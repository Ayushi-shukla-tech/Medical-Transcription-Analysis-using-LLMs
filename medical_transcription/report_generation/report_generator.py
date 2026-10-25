import json
import logging
import time
from datetime import date
import os
import google.generativeai as genai
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

class ReportGenerator:
    """
    A class to handle medical report generation using Google's Gemini model.
    """
    
    def __init__(self, model_name="gemini-2.5-flash"):
        """
        Initialize the ReportGenerator with a specific model.
        
        Args:
            model_name (str): Name of the Gemini model to use.
        """
        logger.info(f"Initializing ReportGenerator with model: {model_name}")
        self.model_name = model_name
        self.model = None
        load_dotenv()
        # Get API key from environment variable
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.warning("GOOGLE_API_KEY not found in environment variables")
        else:
            self.configure_api(api_key)
    
    def configure_api(self, api_key):
        """
        Configure the Gemini API with the given API key.
        
        Args:
            api_key (str): Google API key
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(self.model_name)
            logger.info("Gemini API configured successfully")
            return True
        except Exception as e:
            logger.error(f"Error configuring Gemini API: {str(e)}")
            return False
    
    # Sections of the conversation summary, in display order: (JSON key, heading)
    SUMMARY_SECTIONS = [
        ("patient_reported", "Patient reported"),
        ("doctor_said", "Doctor's assessment & advice"),
        ("next_steps", "Next steps"),
    ]
    # Structured lists returned alongside the summary
    SUMMARY_LISTS = ["symptoms", "medications", "tests", "precautions", "causes"]

    def summarize_conversation(self, transcript, retries=3, delay=5):
        """
        Summarize a doctor-patient conversation into a short list of key points.

        Args:
            transcript (str): Raw transcript of the conversation (no speaker labels)
            retries (int): Number of retries if generation fails
            delay (int): Delay between retries in seconds

        Returns:
            dict or None: {"summary": str, "symptoms": [...], "medications": [...], "tests": [...],
            "precautions": [...], "causes": [...]}, where "summary" is plain text with one heading
            per section followed by "- " bullets. None if Gemini is unavailable.
        """
        prompt = f"""
        You are a medical scribe. Below is an automatic transcript of a conversation between a doctor and a patient.
        The transcript has no speaker labels, so work out who is speaking from context.

        Return ONLY a JSON object (no markdown, no code fences) with these keys:
        - "patient_reported": what the patient said about their symptoms, duration, history and concerns
        - "doctor_said": what the doctor said about those symptoms: assessment, likely cause or diagnosis, advice, prescriptions
        - "next_steps": tests, follow-up or instructions agreed on
        - "symptoms", "medications", "tests", "precautions", "causes": short names only (e.g. "headache", "paracetamol 500mg")

        Rules:
        - Every value is a list of strings. Use an empty list when the conversation does not cover it.
        - Keep it short: at most 4 bullets per section, each bullet under 20 words.
        - Include only what was actually said. Do not invent details or add your own medical advice.

        Transcript:
        \"\"\"{transcript}\"\"\"
        """

        for i in range(retries):
            try:
                if self.model is None:
                    logger.error("Gemini model not initialized. Check API key.")
                    return None

                logger.info("Summarizing conversation with Gemini")
                response = self.model.generate_content(prompt)
                data = self._parse_json(response.text)

                lines = []
                for key, heading in self.SUMMARY_SECTIONS:
                    points = [str(p).strip() for p in data.get(key) or [] if str(p).strip()]
                    if points:
                        lines.append(f"{heading}:")
                        lines.extend(f"- {p}" for p in points)
                        lines.append("")

                result = {"summary": "\n".join(lines).strip() or "No medical discussion was found in this recording."}
                for key in self.SUMMARY_LISTS:
                    result[key] = [str(v).strip() for v in data.get(key) or [] if str(v).strip()]

                logger.info("Conversation summary complete")
                return result
            except Exception as e:
                logger.error(f"Error summarizing conversation: {e}. Retrying in {delay} seconds...")
                time.sleep(delay)

        return None

    @staticmethod
    def _parse_json(text):
        """Parse a JSON object from a model response, tolerating ```json fences around it."""
        text = text.strip()
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end == -1:
            raise ValueError("No JSON object in model response")
        return json.loads(text[start:end + 1])

    def generate_report(self, entities, summary, patient_name=None, patient_age=None, patient_sex=None,
                        physician=None, retries=3, delay=5):
        """
        Generate a clinical report based on entities and summary.

        Args:
            entities (str or list): Extracted medical entities
            summary (str): Summarized medical conversation
            patient_name (str): Patient's name, if known
            patient_age (int): Patient's age, if known
            patient_sex (str): Patient's sex, if known
            physician (str): Treating doctor's name, if known
            retries (int): Number of retries if generation fails
            delay (int): Delay between retries in seconds

        Returns:
            str: Generated clinical report
        """
        # Format entities if they're in list form
        if isinstance(entities, list):
            entities_text = ", ".join([f"{e['term']} ({e['type']})" for e in entities])
        else:
            entities_text = str(entities)

        prompt = f"""
        You are an expert medical assistant tasked with generating a detailed and structured clinical report. Based on the extracted medical entities and summarized findings from a doctor-patient conversation, provide a well-formatted report. Follow this structure:

        ### **Patient Clinical Report**
        **Patient Information:**
        - Name: {patient_name or '[If available]'}
        - Age: {patient_age or '[If available]'}
        - Gender: {patient_sex or '[If available]'}
        - Date of Visit: {date.today().strftime('%d %B %Y')}  
        - Physician: {physician or '[If available]'}  
        
        ### **Chief Complaint & History:**  
        - **Primary Symptoms:** {entities_text}  
        - **Medical History:** [Include relevant history if mentioned]  
        - **Medications:** [Any current medications]  
        - **Allergies:** [List allergies if specified]  
        
        ### **Examination Findings & Observations:**  
        - **Vital Signs:** [If available, include BP, HR, Temperature, etc.]  
        - **Physical Examination Findings:** [Summarized key observations]  
        - **Lab & Imaging Results:** [If applicable, summarize any relevant findings]  
        
        ### **Assessment & Diagnosis:**  
        - **Provisional Diagnosis:** [Provide likely diagnosis based on the data]  
        - **Differential Diagnosis:** [Mention other possible conditions]  
        - **Clinical Justification:** {summary}  
        
        ### **Treatment Plan & Recommendations:**  
        - **Medications Prescribed:** [List medicines with dosage]  
        - **Diagnostic Tests Advised:** [Any further tests recommended]  
        - **Lifestyle & Dietary Recommendations:** [If applicable]  
        - **Follow-up Instructions:** [Next steps and monitoring plan]  
        
        ### **Additional Notes & Explanations:**  
        - Provide **simple explanations** for complex medical terms in the report.  
        """
        
        for i in range(retries):
            try:
                if self.model is None:
                    logger.error("Gemini model not initialized. Check API key.")
                    return "Error: Gemini model not initialized. Check API key."
                
                logger.info("Generating clinical report with Gemini")
                response = self.model.generate_content(prompt)
                logger.info("Report generation complete")
                
                return response.text  # Extract the generated text
            except Exception as e:
                logger.error(f"Error generating report: {e}. Retrying in {delay} seconds...")
                time.sleep(delay)
        
        return "Service is temporarily unavailable. Please try again later."
    
    def explain_medical_terms(self, text, retries=3, delay=5):
        """
        Explain medical terms in simple language.
        
        Args:
            text (str): Text containing medical terms to explain
            retries (int): Number of retries if generation fails
            delay (int): Delay between retries in seconds
            
        Returns:
            str: Explanations of medical terms
        """
        prompt = f"""
        Explain the following medical terms in a simple and easy-to-understand way: "{text}".
        
        **Requirements:**
        - Provide a concise yet informative definition.
        - Explain in layman's terms (avoid medical jargon).
        - If applicable, include causes, symptoms, and common treatments.
        - If multiple terms exist, list explanations separately.
        - Keep it structured and formatted properly.

        Example:
        **Term:** Hypertension  
        **Explanation:** Hypertension (high blood pressure) occurs when the force of blood against artery walls is too high. It can be caused by stress, poor diet, or genetics. It increases the risk of heart disease and stroke. Treatments include lifestyle changes and medication.
        """
        
        for i in range(retries):
            try:
                if self.model is None:
                    logger.error("Gemini model not initialized. Check API key.")
                    return "Error: Gemini model not initialized. Check API key."
                
                logger.info("Generating medical term explanations with Gemini")
                response = self.model.generate_content(prompt)
                logger.info("Explanation generation complete")
                
                return response.text
            except Exception as e:
                logger.error(f"Error generating explanations: {e}. Retrying in {delay} seconds...")
                time.sleep(delay)
        
        return "Service is temporarily unavailable. Please try again later."
    
    def save_report_as_pdf(self, report_text, filename="clinical_report.pdf"):
        """
        Save the generated report as a PDF file.
        
        Args:
            report_text (str): The report text to save
            filename (str): Name of the PDF file
            
        Returns:
            bool: True if successful, False otherwise
        """
        try:
            doc = SimpleDocTemplate(filename, pagesize=letter)
            styles = getSampleStyleSheet()
            elements = []
            
            elements.append(Paragraph("<b>Patient Clinical Report</b>", styles['Title']))
            elements.append(Spacer(1, 12))
            
            for line in report_text.split("\n"):
                if line.strip():  # Skip empty lines
                    # Check if line is a header
                    if line.startswith("###"):
                        elements.append(Paragraph(line.replace("###", ""), styles['Heading1']))
                    elif line.startswith("**") and line.endswith("**"):
                        elements.append(Paragraph(line, styles['Heading2']))
                    else:
                        elements.append(Paragraph(line, styles['Normal']))
                    
                    elements.append(Spacer(1, 6))
            
            doc.build(elements)
            logger.info(f"Report saved as {filename}")
            return True
        except Exception as e:
            logger.error(f"Error saving report as PDF: {str(e)}")
            return False

# Example usage
if __name__ == "__main__":
    # Load environment variables from .env file
    load_dotenv()
    
    # Get API key from environment variable
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("Warning: GOOGLE_API_KEY not found in environment variables")
        print("Please set it in your .env file or export it directly")
    else:
        print(f"Using Google API key from environment variables")
    
    generator = ReportGenerator()
    
    sample_entities = [
        {"term": "headache", "type": "SYMPTOM", "score": 0.95},
        {"term": "nausea", "type": "SYMPTOM", "score": 0.92},
        {"term": "migraine", "type": "DIAGNOSIS", "score": 0.85}
    ]
    
    sample_summary = "Patient reported severe headaches for the past week with throbbing pain on the right side, worsened by light. Also experiencing nausea and vomiting. Doctor diagnosed migraines and discussed treatment options."
    
    report = generator.generate_report(sample_entities, sample_summary)
    
    if report and not report.startswith("Error") and not report.startswith("Service"):
        generator.save_report_as_pdf(report)
        
        # Also generate explanations for medical terms
        explanations = generator.explain_medical_terms("migraine, nausea")
        print(explanations) 