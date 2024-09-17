from collections import defaultdict
import math
import os

def get_trigrams(line):
    return [line[i : i + 3] for i in range(len(line) - 2)]

index = defaultdict(list)

# read all python files in .
DIR = "./pages/posts/"
id2line = {}
doc_lengths = {}

for root, dirs, files in os.walk(DIR):
    for file in files:
        if file.endswith(".md"):
            with open(os.path.join(root, file), "r") as file:
                code = file.read()

            code_lines = code.split("\n")
            total_lines = len(code_lines)

            for line_num, line in enumerate(code_lines):
                trigrams = get_trigrams(line)

                if len(trigrams) == 0:
                    id2line[f"{file.name}:{line_num}"] = line

                for trigram in trigrams:
                    index[trigram].append((file, line_num))
                    id2line[f"{file.name}:{line_num}"] = line

            doc_lengths[file.name] = total_lines

query = "coffee"
context = 0

trigrams = get_trigrams(query)

candidates = set(index[trigrams[0]])
# print([file.name + ":" + str(line_num) for file, line_num in candidates])
for trigram in trigrams:
    candidates = candidates.intersection(set(index[trigram]))

for file, line_num in candidates:
    print(f"{file.name}:{line_num}")
    for i in range(max(0, line_num - context), min(doc_lengths[file.name], line_num + context + 1)):
        line = id2line[f"{file.name}:{i}"]
        print(f"{i}: {line}")

    print()