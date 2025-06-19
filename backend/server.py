from flask import Flask, jsonify, request, Response
from flask_cors import CORS
from transformers import pipeline, AutoTokenizer, AutoModelForTokenClassification
import re
import json
import os
import logging

import google.generativeai as genai
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
import numpy as np

# Add these imports at the top of the file
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from nltk.tokenize import sent_tokenize
import nltk
import ssl
from langchain_google_genai import GoogleGenerativeAI
from langchain.chains import ConversationalRetrievalChain
from langchain.memory import ConversationBufferMemory
import requests

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
import google.oauth2.credentials
import google_auth_oauthlib.flow
import http.client


# Disable SSL verification (use with caution)
try:
    _create_unverified_https_context = ssl._create_unverified_context
except AttributeError:
    pass
else:

    ssl._create_default_https_context = _create_unverified_https_context

# Download NLTK data
nltk.download('punkt', quiet=True)

logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

app = Flask(__name__)
CORS(app, resources={r"/api/*": {"origins": "http://localhost:3000"}})
# CORS(app, resources={r"/*": {"origins": "*"}}) # Allow all origins for now as i have to debug youtube data apis
 

# Set up Google GenerativeAI with your API key
genai.configure(api_key=os.environ.get('GEMINI_API_KEY'))
 

# Initialize the NLP pipeline for sentence segmentation
tokenizer = AutoTokenizer.from_pretrained("jean-baptiste/roberta-large-ner-english")
model = AutoModelForTokenClassification.from_pretrained("jean-baptiste/roberta-large-ner-english")
nlp = pipeline("ner", model=model, tokenizer=tokenizer, aggregation_strategy="simple")

# Initialize Gemini Pro
llm = GoogleGenerativeAI(model="gemini-flash", google_api_key=os.environ.get('GEMINI_API_KEY'), temperature=0.5)
logger.debug("Gemini Pro LLM initialized with temperature 0.5")

# Global variables
conversation_chain = None
vectorstore = None
is_initialized = False
 
def find_start_time(chunk_text, original_transcript):
    # Find the first sentence of the chunk in the original transcript
    first_sentence = simple_sentence_tokenize(chunk_text)[0]
    for entry in original_transcript:
        if first_sentence in entry['text']:
            return entry['start']
    return 0  # Default to 0 if not found

def estimate_duration(chunk_text, original_transcript):
    # Estimate duration based on word count ratio
    chunk_word_count = len(chunk_text.split())
    total_word_count = sum(len(entry['text'].split()) for entry in original_transcript)
    total_duration = sum(entry['duration'] for entry in original_transcript)
    return (chunk_word_count / total_word_count) * total_duration

def initialize_conversation_chain(transcript):
    global conversation_chain, vectorstore, is_initialized
    
    logger.debug("Initializing conversation chain")
    
    try:
        # Create embeddings
        embeddings = HuggingFaceEmbeddings()
        
        # Create a text splitter with optimized settings
        text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,  # Reduced chunk size for more granular context
            chunk_overlap=200,  # Increased overlap for better context preservation
            separators=["\n\n", "\n", ".", "!", "?", ",", " ", ""],
            length_function=len,
        )
        
        # Enhance transcript context with timestamps and structure
        processed_text = []
        for entry in transcript:
            timestamp = formatTimestamp(entry['start'])
            processed_text.append(f"[{timestamp}] {entry['text']}")
        
        full_text = "\n".join(processed_text)
        
        # Split the transcript into chunks
        texts = text_splitter.split_text(full_text)
        
        # Create enhanced metadata
        metadatas = []
        for i, chunk in enumerate(texts):
            # Find the closest transcript entry for timing info
            start_time = 0
            for entry in transcript:
                if entry['text'] in chunk:
                    start_time = entry['start']
                    break
            
            metadatas.append({
                'start': start_time,
                'chunk_id': i,
                'source': 'transcript'
            })
        
        # Create FAISS index with enhanced retrieval
        vectorstore = FAISS.from_texts(texts, embeddings, metadatas=metadatas)
        
        # Initialize conversation memory with system prompt
        memory = ConversationBufferMemory(
            memory_key="chat_history",
            output_key="answer",
            return_messages=True,
            input_key="question"
        )
        
        # Create conversation chain with enhanced retrieval
        conversation_chain = ConversationalRetrievalChain.from_llm(
            llm=llm,
            retriever=vectorstore.as_retriever(
                search_kwargs={
                    "k": 5,  # Number of relevant chunks to retrieve
                    "fetch_k": 10,  # Fetch more candidates before filtering
                }
            ),
            memory=memory,
            return_source_documents=True,
            verbose=True
        )
        
        is_initialized = True
        logger.debug("Conversation chain initialized successfully")
        
    except Exception as e:
        logger.error(f"Error initializing conversation chain: {e}")
        raise e

def formatTimestamp(seconds):
    """Convert seconds to HH:MM:SS format"""
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    
    # Only show HH:MM:SS if hours > 0, otherwise MM:SS
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{secs:02d}"
    return f"{minutes:02d}:{secs:02d}"
 

def generate_answer_progress(user_question):
    try:
        logger.debug("Starting anwer generation")
        # yield "data: " + json.dumps({"progress": 10, "status": "Preparing answer"}) + "\n\n"
 
        # Enhanced context retrieval with English language instruction
        prompt = f"""You are an AI assistant analyzing a csv dataset of CRM data.
    Provide a clear and detailed answer in English to the following question: "{user_question}" 
         
    The dataset is as follows:
```sales_pipeline.csv
opportunity_id,sales_agent,product,account,deal_stage,engage_date,close_date,close_value
1C1I7A6R,Moses Frase,GTX Plus Basic,Cancity,Won,2016-10-20,2017-03-01,1054
Z063OYW0,Darcel Schlecht,GTXPro,Isdom,Won,2016-10-25,2017-03-11,4514
EC4QE1BX,Darcel Schlecht,MG Special,Cancity,Won,2016-10-25,2017-03-07,50
MV1LWRNH,Moses Frase,GTX Basic,Codehow,Won,2016-10-25,2017-03-09,588
PE84CX4O,Zane Levy,GTX Basic,Hatfan,Won,2016-10-25,2017-03-02,517
ZNBS69V1,Anna Snelling,MG Special,Ron-tech,Won,2016-10-29,2017-03-01,49
9ME3374G,Vicki Laflamme,MG Special,J-Texon,Won,2016-10-30,2017-03-02,57
7GN8Q4LL,Markita Hansen,GTX Basic,Cheers,Won,2016-11-01,2017-03-07,601
OLK9LKZB,Niesha Huffines,GTX Plus Basic,Zumgoity,Won,2016-11-01,2017-03-03,1026
HAXMC4IX,James Ascencio,MG Advanced,,Engaging,2016-11-03,,
NL3JZH1Z,Anna Snelling,MG Special,Bioholding,Won,2016-11-04,2017-03-10,53
KWVA7VR1,Gladys Colclough,GTXPro,Genco Pura Olive Oil Company,Lost,2016-11-04,2017-03-18,0
S8DX3XOU,James Ascencio,GTX Plus Pro,Sunnamplex,Won,2016-11-04,2017-03-10,5169
ENB2XD8G,Maureen Marcano,GTX Plus Pro,Sonron,Won,2016-11-04,2017-03-06,4631
09YE9QOV,Hayden Neloms,MG Advanced,Finjob,Won,2016-11-05,2017-03-11,3393
3F5MZNEH,Rosalina Dieter,MG Special,Sonron,Lost,2016-11-05,2017-03-03,0
M6WEJXC0,Rosalina Dieter,MG Advanced,Scotfind,Won,2016-11-05,2017-03-06,3284
6PTR7VBR,Versie Hillebrand,MG Special,Treequote,Won,2016-11-06,2017-03-05,61
902REDPA,Daniell Hammack,GTXPro,Xx-zobam,Lost,2016-11-07,2017-03-09,0
5J9CMGDV,Elease Gluck,MG Special,Rantouch,Won,2016-11-07,2017-03-08,46
JJXRR8R6,James Ascencio,GTX Plus Pro,Fasehatice,Lost,2016-11-07,2017-03-17,0
WF4HA5NW,Moses Frase,MG Special,Ron-tech,Won,2016-11-07,2017-03-18,50
C5K2JP1H,Violet Mclelland,GTX Plus Basic,Vehement Capital Partners,Won,2016-11-07,2017-03-11,1014
ADRB8OMB,Darcel Schlecht,GTX Basic,Warephase,Won,2016-11-08,2017-03-26,561
SBCR987L,Kami Bicknell,GTX Basic,Zoomit,Won,2016-11-10,2017-03-23,590
UP409DSB,Maureen Marcano,MG Advanced,Ganjaflex,Engaging,2016-11-10,,
JSD4APT2,Versie Hillebrand,MG Special,Bioholding,Won,2016-11-10,2017-03-12,61
AO9Z2D17,Violet Mclelland,GTX Plus Pro,Xx-zobam,Lost,2016-11-10,2017-03-11,0
5M58DTJK,Elease Gluck,MG Special,Cheers,Won,2016-11-11,2017-03-05,58
KNY1OSAB,Maureen Marcano,GTXPro,Labdrill,Won,2016-11-11,2017-03-14,4899
EAZDUUM9,Rosie Papadopoulos,MG Advanced,Zotware,Lost,2016-11-11,2017-03-01,0
2STUSOFE,Versie Hillebrand,MG Special,dambase,Won,2016-11-11,2017-03-03,67
JYKM0B00,James Ascencio,GTXPro,Xx-holding,Won,2016-11-12,2017-03-06,4338
KU28360J,Kary Hendrixson,GTX Basic,Fasehatice,Won,2016-11-12,2017-03-19,578
N4SD17JR,Reed Clapper,GTX Basic,Acme Corporation,Won,2016-11-12,2017-03-01,556
E67P9Y3Q,Rosalina Dieter,GTX Basic,Green-Plus,Won,2016-11-12,2017-03-03,635
AT3MMVIS,Wilburn Farren,MG Advanced,The New York Inquirer,Won,2016-11-12,2017-03-07,3045
REJ11LRY,Garret Kinder,GTX Plus Basic,Mathtouch,Won,2016-11-13,2017-03-14,1233
ERV0CAZ7,Versie Hillebrand,MG Special,Zumgoity,Won,2016-11-13,2017-03-09,60
8SOQADK7,Anna Snelling,MG Special,Gogozoom,Lost,2016-11-14,2017-03-30,0
TCHFT25B,Darcel Schlecht,GTX Basic,Stanredtax,Lost,2016-11-14,2017-03-08,0
CZVN09WN,Darcel Schlecht,GTX Plus Basic,Konmatfix,Won,2016-11-14,2017-03-20,1170
EG7OFLFR,Kami Bicknell,GTX Basic,,Engaging,2016-11-14,,
30UQWUKB,Marty Freudenburg,GTX Plus Basic,Genco Pura Olive Oil Company,Won,2016-11-15,2017-03-20,1162
OLVI7L8M,Cassey Cress,GTXPro,,Engaging,2016-11-16,,
97UN20YY,Darcel Schlecht,MG Advanced,Conecom,Won,2016-11-16,2017-03-14,3725
JXLERZ9O,Kary Hendrixson,GTX Basic,Golddex,Won,2016-11-16,2017-03-31,559
6ROE69W5,Rosalina Dieter,GTX Basic,Plexzap,Lost,2016-11-16,2017-03-11,0
0DFXFKT7,Darcel Schlecht,GTX Plus Basic,Rundofase,Lost,2016-11-17,2017-03-21,0
XKMZVSN4,James Ascencio,GTX Plus Pro,Sonron,Won,2016-11-17,2017-03-05,4667
IU8V0BZK,Marty Freudenburg,GTX Plus Basic,Finhigh,Won,2016-11-17,2017-03-17,903
XY42936P,Maureen Marcano,GTX Plus Basic,Finjob,Won,2016-11-17,2017-03-13,1180
XRN54MBM,Niesha Huffines,GTX Basic,Ron-tech,Won,2016-11-17,2017-03-05,487
2V848WZD,Lajuana Vencill,MG Advanced,Stanredtax,Won,2016-11-18,2017-03-04,3180
ONYNTUCG,Darcel Schlecht,GTXPro,Funholding,Lost,2016-11-19,2017-03-17,0
HIOHX80Y,Darcel Schlecht,MG Advanced,Gogozoom,Won,2016-11-19,2017-03-18,3563
F5U1ACDD,Kami Bicknell,GTX Plus Basic,,Engaging,2016-11-19,,
LPKT07PV,Boris Faz,GTXPro,Opentech,Won,2016-11-20,2017-03-23,4704
WPB2SLIG,Donn Cantrell,GTX Plus Pro,Silis,Won,2016-11-20,2017-03-14,5585
XUSUEAV7,Elease Gluck,GTK 500,Zoomit,Won,2016-11-20,2017-03-09,25897
ZZY4516R,Hayden Neloms,MG Advanced,,Engaging,2016-11-20,,
3TYPII47,Kami Bicknell,GTX Plus Basic,Goodsilron,Won,2016-11-20,2017-03-03,1207
7WAX8Z8O,Lajuana Vencill,MG Advanced,Cancity,Lost,2016-11-20,2017-03-08,0
MYDUMR3R,Lajuana Vencill,GTX Basic,Rangreen,Won,2016-11-20,2017-03-04,559
0DRC1U9Q,Maureen Marcano,GTX Basic,Green-Plus,Engaging,2016-11-20,,
37JFKD4I,Niesha Huffines,GTX Plus Basic,dambase,Won,2016-11-20,2017-03-09,1033
25YKPHX8,Donn Cantrell,GTX Basic,Kan-code,Won,2016-11-21,2017-03-21,462
BXXMA7F3,Hayden Neloms,MG Advanced,Nam-zim,Lost,2016-11-21,2017-03-01,0
GIUUTBXM,Kary Hendrixson,GTXPro,Y-corporation,Won,2016-11-21,2017-03-14,5539
MFX2LR1Q,Lajuana Vencill,MG Advanced,Ron-tech,Won,2016-11-21,2017-03-15,3573
DUHE9FLY,Marty Freudenburg,GTXPro,Conecom,Won,2016-11-21,2017-03-01,4926
96BSG7R1,Zane Levy,GTX Plus Basic,Sunnamplex,Lost,2016-11-21,2017-03-17,0
7FQMSWIX,Corliss Cosme,MG Special,Bioplex,Won,2016-11-22,2017-03-04,62
C20AVXN7,Darcel Schlecht,GTXPro,Gogozoom,Won,2016-11-22,2017-03-14,4359
GS1QVWCR,Kami Bicknell,GTX Basic,Plusstrip,Won,2016-11-22,2017-03-31,566
ZWH8FXY3,Marty Freudenburg,GTX Basic,Toughzap,Won,2016-11-22,2017-03-03,508
2U94Y3Q9,Rosie Papadopoulos,MG Advanced,Vehement Capital Partners,Lost,2016-11-22,2017-03-20,0
AAR79NOO,Versie Hillebrand,MG Special,Codehow,Won,2016-11-22,2017-03-11,51
B6B0PNR2,Vicki Laflamme,GTXPro,Dalttechnology,Won,2016-11-22,2017-03-05,4899
M7I5O9YU,Corliss Cosme,GTX Basic,Cheers,Engaging,2016-11-23,,
LXZA2OSZ,Corliss Cosme,GTX Plus Pro,Ontomedia,Won,2016-11-23,2017-03-03,5790
N0ONCYVZ,Donn Cantrell,MG Special,Kinnamplus,Lost,2016-11-23,2017-03-30,0
GYB4W2AU,Elease Gluck,MG Advanced,,Engaging,2016-11-23,,
513DPFX5,Gladys Colclough,GTXPro,Codehow,Won,2016-11-23,2017-03-03,4438
RU023K5W,Gladys Colclough,MG Advanced,Finhigh,Won,2016-11-23,2017-03-17,2972
VDIU10RV,Markita Hansen,MG Special,Lexiqvolax,Engaging,2016-11-23,,
BZCBQ514,Markita Hansen,GTX Basic,Y-corporation,Won,2016-11-23,2017-03-01,523
HEE6P0QH,Anna Snelling,MG Advanced,Statholdings,Won,2016-11-24,2017-03-25,3647
L8CHRJ2B,Cassey Cress,MG Advanced,Umbrella Corporation,Won,2016-11-24,2017-03-01,4200
579LZ3F9,Daniell Hammack,GTX Plus Basic,J-Texon,Engaging,2016-11-24,,
SU8JNMP4,Kami Bicknell,GTX Plus Basic,Bubba Gump,Engaging,2016-11-24,,
V2X2KMUR,Kami Bicknell,GTX Plus Basic,Faxquote,Won,2016-11-24,2017-03-28,1059
AJIPJP75,Marty Freudenburg,GTX Plus Basic,Codehow,Lost,2016-11-24,2017-03-05,0
NYVA2G6U,Versie Hillebrand,MG Special,Dontechi,Won,2016-11-24,2017-03-02,57
FF45BXTL,Vicki Laflamme,MG Advanced,Konex,Won,2016-11-24,2017-03-27,3671
TTA9LYBS,Anna Snelling,MG Special,Treequote,Won,2016-11-25,2017-03-01,58
PAGZQH8L,Cecily Lampkin,MG Advanced,Treequote,Won,2016-11-25,2017-03-06,3956
J7YF6DS7,Corliss Cosme,GTX Plus Pro,Betasoloin,Won,2016-11-25,2017-03-01,5964
S5IXY4Z9,Corliss Cosme,GTXPro,Betasoloin,Won,2016-11-25,2017-03-06,4570
```


```accounts.csv
account,sector,year_established,revenue,employees,office_location,subsidiary_of
Acme Corporation,technolgy,1996,1100.04,2822,United States,
Betasoloin,medical,1999,251.41,495,United States,
Betatech,medical,1986,647.18,1185,Kenya,
Bioholding,medical,2012,587.34,1356,Philipines,
Bioplex,medical,1991,326.82,1016,United States,
Blackzim,retail,2009,497.11,1588,United States,
Bluth Company,technolgy,1993,1242.32,3027,United States,Acme Corporation
Bubba Gump,software,2002,987.39,2253,United States,
Cancity,retail,2001,718.62,2448,United States,
Cheers,entertainment,1993,4269.9,6472,United States,Massive Dynamic
Codehow,software,1998,2714.9,2641,United States,Acme Corporation
Condax,medical,2017,4.54,9,United States,
Conecom,technolgy,2005,1520.66,1806,United States,
Dalttechnology,software,2013,98.79,96,United States,Bubba Gump
dambase,marketing,1995,2173.98,2928,United States,Inity
Domzoom,entertainment,1998,217.87,551,United States,
Doncon,technolgy,2010,587.72,1501,United States,
Donquadtech,technolgy,1992,1712.68,3194,United States,Acme Corporation
Dontechi,software,1982,4618,10083,United States,
Donware,marketing,1999,1197.44,2570,United States,
Fasehatice,retail,1990,4968.91,7523,United States,
Faxquote,telecommunications,1995,1825.82,5595,United States,Sonron
Finhigh,finance,2006,1102.43,1759,United States,
Finjob,employment,1988,2059.9,3644,United States,
Funholding,finance,1991,2819.5,7227,United States,Golddex
Ganjaflex,retail,1995,5158.71,17479,Japan,
Gekko & Co,retail,1990,2520.83,3502,United States,
Genco Pura Olive Oil Company,retail,2007,894.33,1635,Italy,
Globex Corporation,technolgy,2000,1223.72,2497,Norway,
Gogozoom,telecommunications,2007,86.68,187,United States,Sonron
Golddex,finance,2008,52.5,165,United States,
Goodsilron,marketing,2000,2952.73,5107,United States,
Green-Plus,services,2003,692.19,1922,United States,
Groovestreet,retail,2003,223.8,299,United States,
Hatfan,services,1982,792.46,1299,United States,
Hottechi,technolgy,1997,8170.38,16499,Korea,
Initech,telecommunications,1994,6395.05,20275,United States,
Inity,marketing,1986,2403.58,8801,United States,
Isdom,medical,2002,3178.24,4540,United States,
Iselectrics,technolgy,2011,527.11,1428,United States,Acme Corporation
J-Texon,retail,1989,1388.67,3583,United States,
Kan-code,software,1982,11698.03,34288,United States,
Kinnamplus,retail,2004,702.72,1831,United States,
Konex,technolgy,1980,7708.38,13756,United States,
Konmatfix,marketing,1985,375.43,1190,United States,
Labdrill,medical,1985,2741.37,9226,United States,
Lexiqvolax,medical,2004,1618.89,3889,United States,
Massive Dynamic,entertainment,1989,665.06,1095,United States,
Mathtouch,marketing,1984,3027.46,9516,Jordan,
Nam-zim,services,1987,405.59,1179,Brazil,Warephase
Newex,services,1991,1012.72,3492,Germany,
Ontomedia,employment,1997,882.12,2769,United States,
Opentech,finance,1994,355.23,853,United States,
Plexzap,retail,2001,2437.85,4874,United States,
Plusstrip,entertainment,2002,349.81,315,United States,
Plussunin,retail,2003,1419.98,4018,United States,
Rangreen,technolgy,1987,2938.67,8775,Panama,
Rantouch,telecommunications,1994,1188.42,3015,United States,
Ron-tech,medical,1992,3922.42,6837,United States,
Rundofase,technolgy,1983,1008.06,1238,United States,
Scotfind,software,1996,6354.87,16780,United States,Bubba Gump
Scottech,marketing,2012,45.39,100,United States,Inity
Silis,medical,1994,2818.38,6290,United States,
Singletechno,retail,1996,2214.94,5374,United States,
Sonron,telecommunications,1999,1699.85,5108,United States,
Stanredtax,finance,1987,1698.2,3798,United States,
Statholdings,employment,1997,291.27,586,United States,
Streethex,retail,1988,1376.8,1165,Belgium,
Sumace,retail,2000,167.89,493,Romania,
Sunnamplex,marketing,2008,894.37,1593,Poland,
The New York Inquirer,medical,1996,439.21,792,United States,
Toughzap,retail,1995,332.43,799,United States,
Treequote,telecommunications,1988,5266.09,8595,United States,Sonron
Umbrella Corporation,finance,1998,2022.14,5113,United States,
Vehement Capital Partners,finance,1993,646.1,883,United States,Golddex
Warephase,services,1997,2041.73,5276,United States,
Xx-holding,finance,1993,7537.24,20293,United States,
Xx-zobam,entertainment,1989,3838.39,8274,United States,
Y-corporation,employment,1983,2871.35,9561,United States,
Yearin,retail,2005,2261.05,3851,United States,
Zathunicon,retail,2010,71.12,144,United States,
Zencorporation,technolgy,2011,40.79,142,China,
Zoomit,entertainment,1992,324.19,978,United States,
Zotware,software,1979,4478.47,13809,United States,
Zumgoity,medical,1984,441.08,1210,United States,
```


```products.csv
product,series,sales_price
GTX Basic,GTX,550
GTX Pro,GTX,4821
MG Special,MG,55
MG Advanced,MG,3393
GTX Plus Pro,GTX,5482
GTX Plus Basic,GTX,1096
GTK 500,GTK,26768
```

```sales_teams.csv
sales_agent,manager,regional_office
Anna Snelling,Dustin Brinkmann,Central
Cecily Lampkin,Dustin Brinkmann,Central
Versie Hillebrand,Dustin Brinkmann,Central
Lajuana Vencill,Dustin Brinkmann,Central
Moses Frase,Dustin Brinkmann,Central
Jonathan Berthelot,Melvin Marxen,Central
Marty Freudenburg,Melvin Marxen,Central
Gladys Colclough,Melvin Marxen,Central
Niesha Huffines,Melvin Marxen,Central
Darcel Schlecht,Melvin Marxen,Central
Mei-Mei Johns,Melvin Marxen,Central
Violet Mclelland,Cara Losch,East
Corliss Cosme,Cara Losch,East
Rosie Papadopoulos,Cara Losch,East
Garret Kinder,Cara Losch,East
Wilburn Farren,Cara Losch,East
Elizabeth Anderson,Cara Losch,East
Daniell Hammack,Rocco Neubert,East
Cassey Cress,Rocco Neubert,East
Donn Cantrell,Rocco Neubert,East
Reed Clapper,Rocco Neubert,East
Boris Faz,Rocco Neubert,East
Natalya Ivanova,Rocco Neubert,East
Vicki Laflamme,Celia Rouche,West
Rosalina Dieter,Celia Rouche,West
Hayden Neloms,Celia Rouche,West
Markita Hansen,Celia Rouche,West
Elease Gluck,Celia Rouche,West
Carol Thompson,Celia Rouche,West
James Ascencio,Summer Sewald,West
Kary Hendrixson,Summer Sewald,West
Kami Bicknell,Summer Sewald,West
Zane Levy,Summer Sewald,West
Maureen Marcano,Summer Sewald,West
Carl Lin,Summer Sewald,West
``` 
In the answer text just give me plain text without double asterisks to highlight some text in bold style. I do not need that!!!
"""

        model = genai.GenerativeModel('gemini-2.0-flash-001')
        response = model.generate_content(prompt)
        generated_summary = response.text

        logger.debug(f"Generated answer: {generated_summary}")

        # yield "data: " + json.dumps({"progress": 70, "status": "Adding references"}) + "\n\n"

        # summary_with_references = add_references_to_summary(generated_summary, transcript)

        # logger.debug(f"answer with references: {summary_with_references}")
        # yield "data: " + json.dumps({"progress": 90, "status": "Finalizing summary"}) + "\n\n"

        # final_answer = [{
        #     'text': summary_with_references.strip(),
        #     'ref_id': -1
        # }] 
        # yield   json.dumps({"progress": 100, "status": "Complete", "answer": final_answer}) 
        
        # Clean up and format the response
        response_data = {
            'answer': generated_summary,
            'similar_questions': '',
            'top_chunks': '',
            'no_context': 0
        }
        
        return jsonify(response_data)
    
    except Exception as e:
        logger.error(f"Error in generate_answer_progress: {str(e)}", exc_info=True)
        return jsonify({'error': f"An error occurred: {str(e)}"}), 500
    # except Exception as e:
    #     logger.error(f"Error in generate_summary_progress: {str(e)}", exc_info=True)
    #     yield "data: " + json.dumps({"error": str(e)}) + "\n\n"
   
# Add this function to ensure English responses
def ensure_english_response(prompt):
    """Append instruction to ensure response is in English"""
    english_instruction = "\n\nPlease provide your response in English only."
    return prompt + english_instruction
  
@app.route('/api/chat', methods=['POST'])
def question_answer():
    
    data = request.json
    user_question = data.get('message')
    transcript = " "
    
    if not transcript:
        return jsonify({'error': 'No transcript provided'}), 400

    return generate_answer_progress(user_question)

    
def simple_sentence_tokenize(text):
    """
    Split text into sentences using basic rules.
    
    Args:
        text (str): The text to split into sentences
        
    Returns:
        list: A list of sentences
    """
    # Split on common sentence delimiters
    sentences = re.split(r'(?<=[.!?])\s+', text)
    
    # Further split on semicolons and long comma-separated phrases
    final_sentences = []
    for sentence in sentences:
        # Split on semicolons
        sub_sentences = sentence.split(';')
        for sub in sub_sentences:
            # Split long comma-separated phrases
            if len(sub) > 150 and ',' in sub:
                comma_parts = sub.split(',')
                final_sentences.extend(part.strip() for part in comma_parts if part.strip())
            else:
                final_sentences.append(sub.strip())
    
    # Remove empty sentences and clean up
    final_sentences = [s.strip() for s in final_sentences if s.strip()]
    
    # Log for debugging
    logger.debug(f"Split text into {len(final_sentences)} sentences")
    
    return final_sentences

if __name__ == '__main__':
    app.run(debug=True, port=8080)
