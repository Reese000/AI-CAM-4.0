def rot13_cipher(text: str) -> str:
    result = ""
    for char in text:
        if char.isalpha():
            offset = ord('a') if char.islower() else ord('A')
            result += chr((ord(char) - offset + 13) % 26 + offset)
        else:
            result += char
    return result