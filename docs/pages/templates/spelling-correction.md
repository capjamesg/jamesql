---
layout: default
title: Spelling Correction
permalink: /spelling-correction/
---

It is recommended that you check the spelling of words before you run a query. 

This is because correcting the spelling of a word can improve the accuracy of your search results.

### Correcting the spelling of a single word

To recommend a spelling correction for a query, use the following code:

```python
index = ...

suggestion = index.spelling_correction("taylr swift")
```

This will return a single suggestion. The suggestion will be the word that is most likely to be the correct spelling of the word you provided.

Spelling correction first generates segmentations of a word, like:

- `t aylorswift`
- `ta ylorswift`

If a segmentation is valid, it is returned.

For example, if the user types in `taylorswift`, one permutation would be segmented into `taylor swift`. If `taylor swift` is common in the index, `taylor swift` will be returned as the suggestion.

Spelling correction works by transforming the input query by inserting, deleting, and transforming one character in every position in a string. The transformed strings are then looked up in the index to find if they are present and, if so, how common they are.

The most common suggestion is then returned.

For example, if you provide the word `tayloi` and `taylor` is common in the index, the suggestion will be `taylor`.

If correction was not possible after transforming one character, correction will be attempted with two transformations given the input string.

If the word you provided is already spelled correctly, the suggestion will be the word you provided. If spelling correction is not possible (i.e. the word is too distant from any word in the index), the suggestion will be `None`.

### Correcting a string query

If you are correcting a string query submitted with the `string_query_search()` function, spelling will be automatically corrected using the algorithm above. No configuration is required.