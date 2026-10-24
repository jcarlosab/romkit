"""Conservative evidence for unstructured strings, not indexed text tables."""
import re
import unicodedata


def plausible_text(text):
    latin, japanese, kana, halfwidth, other = 0, 0, 0, 0, 0
    for char in text:
        code = ord(char)
        if char.isalpha():
            if "LATIN" in unicodedata.name(char, ""):
                latin += 1
            elif 0x3040 <= code <= 0x30ff:
                japanese += 1
                kana += 1
            elif 0x3400 <= code <= 0x9fff:
                japanese += 1
            elif 0xff66 <= code <= 0xff9d:
                japanese += 1
                halfwidth += 1
            else:
                other += 1
        elif not (char.isspace() or char.isdecimal() or unicodedata.category(char).startswith("P")
                  or char in "$%&+*=|~^@#_\\"):
            other += 1
    if other or not latin + japanese:
        return False
    if japanese:
        # Random UTF-16 words and halfwidth SJIS bytes are not Japanese evidence.
        return kana >= 2 and japanese >= .6 * (latin + japanese) and halfwidth <= japanese / 3
    stripped = text.strip()
    if not any(char.isspace() for char in stripped) and any(char in stripped for char in "_/\\"):
        return False
    if re.fullmatch(r"[0-9A-Fa-f]{8,}", stripped) and any(c.isdigit() for c in stripped):
        return False
    words = re.findall(r"[^\W\d_]+", stripped, flags=re.UNICODE)
    words = [word for word in words if len(word) >= 2]
    if not words:
        return False
    normalized = [unicodedata.normalize("NFKD", word).casefold() for word in words]
    if sum(any(c in "aeiouy" for c in word) for word in normalized) < max(1, len(words) / 2):
        return False
    letters = "".join(normalized)
    if len(letters) >= 6 and max(letters.count(char) for char in set(letters)) / len(letters) > .65:
        return False
    # Reject mixed-case identifiers and dense punctuation typical of binary noise.
    if any(len(word) >= 6 and sum(a.islower() and b.isupper() for a, b in zip(word, word[1:])) >= 2 for word in words):
        return False
    return sum(c.isalpha() or c.isspace() or c in "'’-.,!?;:{}()[]<>\"" for c in text) >= len(text) * .9
