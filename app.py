import os
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from youtube_transcript_api import YouTubeTranscriptApi, TranscriptsDisabled, NoTranscriptFound
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_core.prompts import PromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.runnables import RunnableParallel, RunnablePassthrough, RunnableLambda
from langchain_core.output_parsers import StrOutputParser
from fastapi.concurrency import run_in_threadpool

# Google API key
os.environ["GOOGLE_API_KEY"] = "Your API Key"

app = FastAPI(title="Dynamic YouTube Q&A Backend (Hindi + English)")

# Enable CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class QuestionRequest(BaseModel):
    video_id: str
    question: str

# Initialize LLM (Using the model that works for you)
llm = ChatGoogleGenerativeAI(model="gemini-2.5-flash")

# --- MODIFICATION 1: Updated Prompt to ask for Links ---
prompt = PromptTemplate(
    template="""
You are a helpful AI assistant.
Answer the question based on the given YouTube video transcript.
The transcript contains timestamps in the format [Time: SECONDS].

Your Goal:
1. Answer the question accurately.
2. For every key point you make, you MUST append a clickable link to the video timestamp.
3. The format for the link is: https://youtu.be/{video_id}?t=SECONDS
4. Present the answer in bullet points.

Example Output format:
* The speaker explains that Python is versatile. [Watch](https://youtu.be/{video_id}?t=120)
* He mentions that memory management is automatic. [Watch](https://youtu.be/{video_id}?t=150)

Context:
{context}

Question:
{question}
""",
    input_variables=["context", "question", "video_id"]
)

# --- MODIFICATION 2: Embed Timestamps in Text ---
def fetch_transcript(video_id: str):
    ytt = YouTubeTranscriptApi()
    
    try:
        transcript_list = ytt.fetch(video_id, languages=["hi"])
    except Exception:
        try:
            transcript_list = ytt.fetch(video_id, languages=["en"])
        except TranscriptsDisabled:
            raise HTTPException(status_code=404, detail="Transcripts are disabled for this video.")
        except NoTranscriptFound:
            raise HTTPException(status_code=404, detail="No transcript found in Hindi or English.")
        except Exception as e:
            print(f"Error fetching transcript: {e}")
            raise HTTPException(status_code=500, detail=f"Error fetching transcript: {e}")
    
    # We join the text, but we PREPEND the timestamp to every snippet.
    # Result looks like: "[Time: 0] Hello everyone [Time: 5] Welcome to the video..."
    transcript_text = " ".join(f"[Time: {int(snippet.start)}] {snippet.text}" for snippet in transcript_list)
    
    return transcript_text

# Create vector store dynamically
def create_dynamic_vector_store(transcript: str):
    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    chunks = splitter.create_documents([transcript])
    embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
    vector_store = FAISS.from_documents(chunks, embeddings)
    return vector_store.as_retriever(search_type="similarity", search_kwargs={"k": 3})

# Cache retrievers for performance
VECTOR_STORE_CACHE = {}
def get_retriever(transcript, video_id):
    if video_id in VECTOR_STORE_CACHE:
        return VECTOR_STORE_CACHE[video_id]
    retriever = create_dynamic_vector_store(transcript)
    VECTOR_STORE_CACHE[video_id] = retriever
    return retriever

# /ask endpoint
@app.post("/ask")
async def ask_question(request: QuestionRequest):
    print(f"Processing video: {request.video_id} | Question: {request.question}") 
    
    transcript_text = fetch_transcript(request.video_id)
    retriever = get_retriever(transcript_text, request.video_id)
    
    # --- MODIFICATION 3: Pass video_id to the prompt ---
    parallel_chain = RunnableParallel({
        "context": retriever | RunnableLambda(lambda docs: "\n\n".join(d.page_content for d in docs)),
        "question": RunnablePassthrough(),
        "video_id": RunnableLambda(lambda x: request.video_id) # Inject video ID here
    })
    
    parser = StrOutputParser()
    main_chain = parallel_chain | prompt | llm | parser
    
    answer_text = await run_in_threadpool(lambda: main_chain.invoke(request.question))
    
    # Simple formatting: Ensure clean bullet points
    formatted_answer = "\n".join(
        [line.strip() for line in answer_text.split("\n") if line.strip()]
    )
    
    return {"answer": formatted_answer}

# Health check
@app.get("/health")
async def health():
    return {"status": "ok"}