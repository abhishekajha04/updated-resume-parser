import streamlit as st
import pandas as pd
import re
from pymongo import MongoClient
import fitz  # PyMuPDF
import spacy

# ----------------------------
# Load SpaCy model safely
# ----------------------------
@st.cache_resource
def load_spacy_model():
    try:
        nlp = spacy.load("en_core_web_sm")
    except OSError:
        # Download the model if it's not already present
        import spacy.cli
        spacy.cli.download("en_core_web_sm")  # Download the model explicitly
        nlp = spacy.load("en_core_web_sm")
    return nlp

nlp = load_spacy_model()


# ----------------------------
# MongoDB Connection
# ----------------------------
@st.cache_resource
def init_connection():
    try:
        client = MongoClient(
            "mongodb+srv://infoolinp:StMxx33r0rolkwIN@hiring-bazzar-db.qocfcad.mongodb.net/?retryWrites=true&w=majority&appName=hiring-bazzar-db"
        )
        info = client.server_info() # Force connection on a request as early as possible
        print(f"MongoDB connected: {info}")
        return client
    except Exception as e:
        print(f"MongoDB connection error: {e}")
        return None

client = init_connection()

if client:  #Checks the connection before initializing the Database object
    db = client["resumeDB"]
    collection = db["parsedResumes"]
else:
    db = None
    collection = None
    st.error("Failed to connect to MongoDB.  Check your connection string and network settings.")


# ----------------------------
# Extract text from PDF
# ----------------------------
def extract_text(pdf_file):
    try:
        doc = fitz.open(stream=pdf_file.read(), filetype="pdf")
        text = ""
        for page in doc:
            text += page.get_text("text")
        return text
    except Exception as e:
        st.error(f"Error extracting text from PDF: {e}")
        return ""

# ----------------------------
# Extract entities from text
# ----------------------------
def extract_entities(text):
    entities = {"NAME": "", "EMAIL": "", "PHONE": "", "SKILLS": [], "EDUCATION": [], "EXPERIENCE": []}

    if not text:  # Handle empty text gracefully
        return entities

    try:
        doc = nlp(text)

        # Name extraction
        lines = text.strip().split("\n")
        if lines:
            first_line = lines[0].strip()
            if len(first_line.split()) <= 4:
                entities["NAME"] = first_line
        
        for ent in doc.ents:
            if ent.label_ == "PERSON" and not entities["NAME"]:
                entities["NAME"] = ent.text

        # Email & Phone
        email_match = re.search(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", text)
        if email_match:
            entities["EMAIL"] = email_match.group()

        phone_match = re.search(r"\+?\d[\d\-\s]{8,15}\d", text)
        if phone_match:
            entities["PHONE"] = phone_match.group()

        # Skills
        skills_db = [
            "Python","Java","C++","C","SQL","Excel","Tableau","PowerBI",
            "Machine Learning","Deep Learning","NLP","TensorFlow","PyTorch",
            "Django","Flask","React","Node.js","AWS","Azure","GCP","Docker",
            "Kubernetes","Git","Linux"
        ]
        found_skills = set()
        for skill in skills_db:
            if re.search(r"\b" + re.escape(skill) + r"\b", text, re.IGNORECASE):
                found_skills.add(skill)
        entities["SKILLS"] = list(found_skills)

        # Education
        education_keywords = [
            "B.Tech","B.E","Bachelor","M.Tech","M.E","M.Sc","B.Sc",
            "MBA","PhD","Diploma","High School","Intermediate","Graduation"
        ]
        found_edu = []
        for line in lines:
            for keyword in education_keywords:
                if re.search(r"\b" + keyword + r"\b", line, re.IGNORECASE):
                    found_edu.append(line.strip())
        entities["EDUCATION"] = list(set(found_edu))

        # Experience
        exp_patterns = re.findall(
            r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?\s?\d{4})",
            text, re.IGNORECASE
        )
        orgs = [ent.text for ent in doc.ents if ent.label_ == "ORG"]
        if orgs:
            entities["EXPERIENCE"].extend(list(set(orgs)))
        if exp_patterns:
            entities["EXPERIENCE"].extend(list(set(exp_patterns)))

        return entities

    except Exception as e:
        st.error(f"Error extracting entities: {e}")
        return entities



# ----------------------------
# Streamlit App UI
# ----------------------------
st.title("📄 Advanced Resume Parser")
st.write("Upload PDF resumes to extract Name, Email, Phone, Skills, Education, Experience.")

uploaded_files = st.file_uploader("Upload PDFs", type="pdf", accept_multiple_files=True)

if uploaded_files:
    all_results = []
    for pdf_file in uploaded_files:
        text = extract_text(pdf_file)
        if text:  #Only process if text extraction was successful
            entities = extract_entities(text)
            all_results.append(entities)
    
    # Display results
    if all_results: #Check for empty sets before generating the pandas dataframe:
        df = pd.DataFrame(all_results)
        st.dataframe(df)

        # Download CSV
        csv = df.to_csv(index=False).encode("utf-8")
        st.download_button("📥 Download CSV", data=csv, file_name="parsed_resumes.csv", mime="text/csv")

        # Upload to MongoDB
        if st.button("📤 Upload to MongoDB"):
            if all_results and collection: #Check if Mongo connection successful:
                collection.insert_many(all_results)
                st.success("✅ Data successfully uploaded to MongoDB!")
            else:
                st.warning("⚠️ No data available to upload, or MongoDB connection failed.")
    else:
        st.warning("⚠️ No resumes were successfully processed.")
