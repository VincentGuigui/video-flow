"""TF-IDF beat labels: the P0 labelling path and the LLM fallback (04 §8, 08 §3).

Each beat is a document (the concatenated texts of its takes). Terms are comparison keys
without fillers, restart cues, stop words and 1-character tokens; the label shows the
first surface form seen for each of the top terms, in order of first appearance.
"""

import math
from collections import Counter
from collections.abc import Mapping, Sequence

from videoflow.analysis.textnorm import FILLERS, Token, lang_key, tokenize


def _lexicon(text: str) -> frozenset[str]:
    return frozenset(text.split())


STOPWORDS: dict[str, frozenset[str]] = {
    "fr": _lexicon(
        """a au aux avec ce ces c cet cette d dans de des du elle en et est etre il ils j je
        l la le les leur lui m ma mais me mes moi mon n ne nous on ou par pas pour qu que
        qui s sa se ses son sur t ta te tes toi ton tu un une vous y ya va vais allons
        aujourd hui alors donc voila voici ca cela ici tres plus aussi comme si tout tous fait faire
        nos notre votre vos sont ont avons avez ai as"""
    ),
    "en": _lexicon(
        """a an and are as at be been but by do does for from going gonna have has he her
        his i if in into is it its just let me my of on or our so that the their them then
        there these they this to too up us was we were what when which will with you your
        here now very also all can get got today"""
    ),
}


def _terms(texts: Sequence[str], language: str) -> list[tuple[str, str]]:
    """(key, surface) pairs of label-worthy words, in order.

    A word split into several tokens ("aujourd'hui", "l'appareil") stays one term; its
    stop-word and elided parts are dropped from both the key and the surface form.
    """
    lang = lang_key(language)
    stop = STOPWORDS[lang] | FILLERS[lang]
    out: list[tuple[str, str]] = []
    for text in texts:
        words = text.split()
        by_word: dict[int, list[Token]] = {}
        for tok in tokenize(words, language):
            by_word.setdefault(tok.word_index, []).append(tok)
        for wi, toks in by_word.items():
            if not all(t.content for t in toks):
                continue
            keep = [t.key for t in toks if t.key not in stop and len(t.key) >= 2]
            if not keep:
                continue
            surface = words[wi].strip('.,;:!?\u2026"()[]').lower().replace("\u2019", "'")
            if len(toks) > 1 and toks[0].key in stop and "'" in surface:
                surface = surface.split("'", 1)[1]
            out.append((" ".join(keep), surface or " ".join(keep)))
    return out


def tfidf_labels(
    beats: Mapping[str, Sequence[str]],
    language: str = "fr",
    top_n: int = 3,
    max_len: int = 48,
) -> dict[str, str]:
    """Label per beat key from the texts of its takes (empty string when no terms)."""
    docs = {key: _terms(texts, language) for key, texts in beats.items()}
    df: Counter[str] = Counter()
    for terms in docs.values():
        df.update({k for k, _ in terms})
    n_docs = max(1, len(docs))

    labels: dict[str, str] = {}
    for key, terms in docs.items():
        tf = Counter(k for k, _ in terms)
        first: dict[str, int] = {}
        surface: dict[str, str] = {}
        for pos, (k, s) in enumerate(terms):
            first.setdefault(k, pos)
            surface.setdefault(k, s)
        scored = sorted(
            tf, key=lambda k: (-tf[k] * (math.log((1 + n_docs) / (1 + df[k])) + 1), first[k])
        )
        chosen = sorted(scored[:top_n], key=lambda k: first[k])
        label = ""
        for k in chosen:
            candidate = f"{label} {surface[k]}".strip()
            if len(candidate) > max_len:
                break
            label = candidate
        labels[key] = label[:1].upper() + label[1:]
    return labels
