# parse.py
import re ## regular expressions

import pymupdf ## library for working with PDF files

def pdf_to_pages(path: str) -> list[dict]: ##takes a file path, returns a list of DICT objects
    doc = pymupdf.open(path) #creates a pdf object called doc
    return [{"page": i + 1, "text": p.get_text()} for i, p in enumerate(doc)] ##going to assume this loops and creates list of {page, text}

def _normalize(text: str) -> str: ## takes in a string, returns a normalized string
    return re.sub(r"\s+", " ", text).strip().lower() ## replaces all whitespace characters (spaces, tabs, newlines) with a single space, removes leading and trailing whitespace, and converts the text to lowercase. This is useful for comparing text in a case-insensitive manner and ignoring differences in whitespace.

def verify_quote(source_quote: str, page_text: str) -> bool: ## takes in a source quote and page text, returns a boolean indicating whether the source quote is present in the page text
    return _normalize(source_quote) in _normalize(page_text) ## checks if the normalized source quote is present in the normalized page text. This allows for a more flexible comparison that ignores differences in case and whitespace.
