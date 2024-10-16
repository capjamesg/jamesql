def normalize_operator_query(t):
    if isinstance(t, str):
        return t

    return "_".join(t)


def simplifier(terms):
    new_terms = []
    outer_terms = set()
    to_remove = set()

    for i, t in enumerate(terms):
        if isinstance(t, str) and t not in outer_terms:
            outer_terms.add(t)
            new_terms.append(t)

    for i, t in enumerate(terms):
        normalized_terms = normalize_operator_query(t)
        if isinstance(t, list) and t[1] == "OR":
            for inner_term in t:
                if inner_term == "OR":
                    continue

                if inner_term not in outer_terms:
                    outer_terms.add(inner_term)
                    new_terms.append(inner_term)
        elif (
            isinstance(t, list)
            and t[1] == "AND"
            and normalized_terms not in outer_terms
        ):
            new_terms.append(t)
            outer_terms.add(normalized_terms)
            if t[0] in outer_terms:
                to_remove.add(t[0])
            if t[2] in outer_terms:
                to_remove.add(t[2])
        elif (
            isinstance(t, list)
            and t[0] == "NOT"
            and normalized_terms not in outer_terms
        ):
            new_terms.append("-" + t[1])

            if t[1] in outer_terms:
                to_remove.add(t[1])
                to_remove.add("-" + t[1])
    
    return [i for i in new_terms if normalize_operator_query(i) not in to_remove]
