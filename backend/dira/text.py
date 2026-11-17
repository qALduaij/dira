import unicodedata


def normalize(text: str) -> str:
    text = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    return text.casefold().translate(str.maketrans({"أ": "ا", "إ": "ا", "آ": "ا", "ى": "ي", "ـ": ""}))
