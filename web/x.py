import spacy

# Load the English NLP model
nlp = spacy.load("en_core_web_sm")

# Parse a sentence
sentences = "The traditional OAuth spec lets you authenticate as a user on one site to another which is useful if you want to use, say, your Google account to create an account on Kaggle. But OAuth is platform-specific. IndieAuth extends OAuth so that you can authenticate to a website using a URL or a domain name. This has a range of applications.".split(". ")
pairs = {}

query = "IndieAuth"

for j, sentence in enumerate(sentences):
    doc = nlp(sentence)

    # create x-y pairs like
    # {indieweb: the indieweb is...

    # if sentence matches the pattern nsubj verb
    # then add the nsubj as key and sentence as value

    if len(doc) == 0:
        continue
    
    for i, token in enumerate(doc):
        if token.pos_ == "PROPN" or (token.text == query and token.pos_ == "NOUN"):
            # if j + 1 < len(sentences):
            pairs[token.text.lower()] = sentence + ". " + sentences[j + 1]

print(pairs.get(query.lower(), "Not found"))