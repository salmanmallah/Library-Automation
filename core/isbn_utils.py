import re
from typing import Optional, Union

def clean_isbn_string(raw_data: Union[str, bytes]) -> str:
    """Decodes bytes if necessary and strips whitespace and separators."""
    if isinstance(raw_data, bytes):
        try:
            text = raw_data.decode("utf-8").strip()
        except UnicodeDecodeError:
            text = raw_data.decode("latin-1", errors="ignore").strip()
    else:
        text = str(raw_data).strip()
    
    # Remove common URL/URN prefixes if barcode contains a URI
    match = re.search(r'(?:isbn(?:=|\/|:))?([0-9Xx\-]{10,17})', text, re.IGNORECASE)
    if match:
        text = match.group(1)
        
    # Remove hyphens and spaces
    cleaned = re.sub(r'[\s\-]+', '', text).upper()
    return cleaned

def is_valid_isbn10(isbn: str) -> bool:
    """Validates ISBN-10 check digit."""
    if len(isbn) != 10:
        return False
    if not (isbn[:-1].isdigit() and (isbn[-1].isdigit() or isbn[-1] == 'X')):
        return False
    
    total = sum((10 - i) * int(c) for i, c in enumerate(isbn[:-1]))
    check = 10 if isbn[-1] == 'X' else int(isbn[-1])
    return (total + check) % 11 == 0

def is_valid_isbn13(isbn: str) -> bool:
    """
    Validates ISBN-13 prefix (Bookland EAN strictly starting with 978 or 979)
    and validates Modulo 10 check digit.
    """
    if len(isbn) != 13 or not isbn.isdigit():
        return False
    
    # Real ISBN-13 ALWAYS begins with 978 or 979
    if not isbn.startswith(('978', '979')):
        return False
    
    total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(isbn))
    return total % 10 == 0

def validate_and_normalize_isbn(raw_data: Union[str, bytes]) -> Optional[str]:
    """
    Cleans raw barcode data and validates whether it is a legitimate ISBN-10 or ISBN-13.
    Rejects barcodes that do not have valid check digits or proper Bookland prefixes.
    """
    cleaned = clean_isbn_string(raw_data)
    if is_valid_isbn13(cleaned) or is_valid_isbn10(cleaned):
        return cleaned
        
    return None
