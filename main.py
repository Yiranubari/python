from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel
import hashlib
from collections import Counter
from datetime import datetime
from dateutil.tz import tzutc
import re

app = FastAPI()

# In-memory storage: key = sha256_hash, value = dict with details
strings_db = {}

class StringInput(BaseModel):
    value: str

class StringResponse(BaseModel):
    id: str
    value: str
    properties: dict
    created_at: str

class StringsListResponse(BaseModel):
    data: list[StringResponse]
    count: int
    filters_applied: dict | None = None
    interpreted_query: dict | None = None

def compute_properties(value: str) -> dict:
    length = len(value)
    is_palindrome = value.lower() == value.lower()[::-1]
    unique_characters = len(set(value))
    word_count = len(value.split())
    sha256_hash = hashlib.sha256(value.encode()).hexdigest()
    character_frequency_map = dict(Counter(value))
    return {
        "length": length,
        "is_palindrome": is_palindrome,
        "unique_characters": unique_characters,
        "word_count": word_count,
        "sha256_hash": sha256_hash,
        "character_frequency_map": character_frequency_map
    }

@app.post("/strings", response_model=StringResponse, status_code=201)
def create_string(input: StringInput):
    if not isinstance(input.value, str):
        raise HTTPException(status_code=422, detail="Invalid data type for 'value' (must be string)")
    if not input.value:
        raise HTTPException(status_code=400, detail="Missing 'value' field")
    
    props = compute_properties(input.value)
    hash_id = props["sha256_hash"]
    if hash_id in strings_db:
        raise HTTPException(status_code=409, detail="String already exists in the system")
    
    created_at = datetime.now(tzutc()).isoformat()
    record = {
        "id": hash_id,
        "value": input.value,
        "properties": props,
        "created_at": created_at
    }
    strings_db[hash_id] = record
    return record

@app.get("/strings/{string_value}", response_model=StringResponse)
def get_string(string_value: str):
    props = compute_properties(string_value)  # Recompute hash based on value
    hash_id = props["sha256_hash"]
    if hash_id not in strings_db:
        raise HTTPException(status_code=404, detail="String does not exist in the system")
    return strings_db[hash_id]

@app.get("/strings", response_model=StringsListResponse)
def get_all_strings(
    is_palindrome: bool | None = Query(None),
    min_length: int | None = Query(None),
    max_length: int | None = Query(None),
    word_count: int | None = Query(None),
    contains_character: str | None = Query(None)
):
    filters = {
        "is_palindrome": is_palindrome,
        "min_length": min_length,
        "max_length": max_length,
        "word_count": word_count,
        "contains_character": contains_character
    }
    # Validate types
    if min_length is not None and not isinstance(min_length, int):
        raise HTTPException(status_code=400, detail="Invalid query parameter values or types")
    if max_length is not None and not isinstance(max_length, int):
        raise HTTPException(status_code=400, detail="Invalid query parameter values or types")
    if word_count is not None and not isinstance(word_count, int):
        raise HTTPException(status_code=400, detail="Invalid query parameter values or types")
    if contains_character is not None and (len(contains_character) != 1 or not contains_character.isalpha()):
        raise HTTPException(status_code=400, detail="Invalid query parameter values or types")
    
    filtered = []
    for record in strings_db.values():
        props = record["properties"]
        if is_palindrome is not None and props["is_palindrome"] != is_palindrome:
            continue
        if min_length is not None and props["length"] < min_length:
            continue
        if max_length is not None and props["length"] > max_length:
            continue
        if word_count is not None and props["word_count"] != word_count:
            continue
        if contains_character is not None and contains_character not in record["value"]:
            continue
        filtered.append(record)
    
    return {
        "data": filtered,
        "count": len(filtered),
        "filters_applied": {k: v for k, v in filters.items() if v is not None}
    }

@app.get("/strings/filter-by-natural-language", response_model=StringsListResponse)
def natural_language_filter(query: str = Query(...)):
    if not query:
        raise HTTPException(status_code=400, detail="Unable to parse natural language query")
    
    # Basic parsing heuristics
    parsed_filters = {}
    lower_query = query.lower()
    
    if "single word" in lower_query:
        parsed_filters["word_count"] = 1
    if "palindromic" in lower_query or "palindrome" in lower_query:
        parsed_filters["is_palindrome"] = True
    if "longer than" in lower_query:
        match = re.search(r"longer than (\d+)", lower_query)
        if match:
            parsed_filters["min_length"] = int(match.group(1)) + 1
    if "containing the letter" in lower_query:
        match = re.search(r"containing the letter (\w)", lower_query)
        if match:
            parsed_filters["contains_character"] = match.group(1)
    if "contain the first vowel" in lower_query:
        parsed_filters["contains_character"] = "a"  # Heuristic for 'first vowel'
    
    if not parsed_filters:
        raise HTTPException(status_code=400, detail="Unable to parse natural language query")
    
    # Apply filters (reuse logic from get_all_strings)
    filtered = []
    for record in strings_db.values():
        props = record["properties"]
        if "is_palindrome" in parsed_filters and props["is_palindrome"] != parsed_filters["is_palindrome"]:
            continue
        if "min_length" in parsed_filters and props["length"] < parsed_filters["min_length"]:
            continue
        if "word_count" in parsed_filters and props["word_count"] != parsed_filters["word_count"]:
            continue
        if "contains_character" in parsed_filters and parsed_filters["contains_character"] not in record["value"]:
            continue
        filtered.append(record)
    
    if not filtered and "conflicting" in lower_query:  # Simple conflict check example
        raise HTTPException(status_code=422, detail="Query parsed but resulted in conflicting filters")
    
    return {
        "data": filtered,
        "count": len(filtered),
        "interpreted_query": {
            "original": query,
            "parsed_filters": parsed_filters
        }
    }

@app.delete("/strings/{string_value}", status_code=204)
def delete_string(string_value: str):
    props = compute_properties(string_value)
    hash_id = props["sha256_hash"]
    if hash_id not in strings_db:
        raise HTTPException(status_code=404, detail="String does not exist in the system")
    del strings_db[hash_id]
    return None