from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel
from typing import List
from transformers import AutoTokenizer, AutoModel
import torch

# ===== CONFIG =====
MODEL_NAME = "intfloat/multilingual-e5-base"
BATCH_SIZE = 4
API_KEY = "MAVAP"  

# ===== LOAD MODEL =====
print(f"Loading model {MODEL_NAME}...")
tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
model = AutoModel.from_pretrained(MODEL_NAME)
model.eval()  # chỉ inference
device = torch.device("cpu")
model.to(device)

# ===== API =====
app = FastAPI(title="Embedding API")

class EmbeddingRequest(BaseModel):
    texts: List[str]

class EmbeddingResponse(BaseModel):
    embeddings: List[List[float]]

def mean_pooling(model_output, attention_mask):
    token_embeddings = model_output.last_hidden_state  # [B, L, D]
    input_mask_expanded = attention_mask.unsqueeze(-1).expand(token_embeddings.size()).float()
    return (token_embeddings * input_mask_expanded).sum(1) / input_mask_expanded.sum(1)

@app.post("/embed", response_model=EmbeddingResponse)
def embed(request: EmbeddingRequest, x_api_key: str = Header(...)):
    # ===== check API key =====
    if x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API Key")
    
    embeddings = []
    texts = request.texts
    for i in range(0, len(texts), BATCH_SIZE):
        batch_texts = texts[i:i+BATCH_SIZE]
        encoded_input = tokenizer(batch_texts, padding=True, truncation=True, return_tensors="pt")
        encoded_input = {k:v.to(device) for k,v in encoded_input.items()}
        with torch.no_grad():
            model_output = model(**encoded_input)
        batch_embeddings = mean_pooling(model_output, encoded_input['attention_mask'])
        batch_embeddings = batch_embeddings.cpu().tolist()
        embeddings.extend(batch_embeddings)
    return {"embeddings": embeddings}
