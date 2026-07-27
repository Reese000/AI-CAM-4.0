def snake_to_camel(text: str) -> str:
    words = text.split('_')
    return words[0] + ''.join(word.title() for word in words[1:])