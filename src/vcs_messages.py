"""Plain scientific feedback for the scientist and its readable trace."""
import re


def plain_feedback(text: str) -> str:
    """Remove coordinator labels without rewriting scientific instructions.

    Native scientist/tool output must not pass through this function. Quoted
    wording is preserved; only known labels and custody-only sentences change.
    """
    text = re.sub(r"(?i)[ \t]*(?:Is claude fish done\?|Btw, what claude do we use\? Sonnet\?)[ \t]*", "", text)
    quotes = []

    def protect(match):
        quotes.append(match.group())
        return f"\ufffcQUOTE{len(quotes) - 1}\ufffc"

    text = re.sub(r'“[^”]*”|"(?:[^"\\]|\\.)*"', protect, text)
    text = re.sub(r"(?im)^[ \t]*Human review of attempt\s+[\w-]+:\s*", "", text)
    text = re.sub(r"(?im)^[ \t]*(?:Human TUI feedback|Human TUI requests revision|Human review|Human follow-up|User instruction|Human clarification of the literature request):\s*", "", text)
    text = re.sub(r"(?im)^[ \t]*Human rejected this candidate:\s*", "", text)
    text = re.sub(r"(?im)^[ \t]*Human instructions?, verbatim:\s*", "", text)
    text = re.sub(r"(?im)^[ \t]*(?:changes required|further changes required|rejected)\.\s*", "", text)
    text = re.sub(r"(?im)^[ \t]*(?:Response to literature request|Primary-source response to request)\s+[a-f0-9]{32,64}\.\s*", "", text)
    text = re.sub(r"(?im)^[ \t]*Operator scientific review under[^.\n]+\.[ \t]*", "", text)
    text = re.sub(r"(?im)^[ \t]*Operator review of this same candidate, under[^\n]+(?:\n|$)", "", text)
    text = re.sub(r"(?i)Delegated assistant scientific review under the user goal to finish the remaining cycles\.\s*", "", text)
    text = text.replace("Formal host verdict is proved with faithful extraction, but this candidate", "This candidate")
    text = re.sub(r"(?i)This is not a claim of personal user inspection\.\s*", "", text)
    text = re.sub(r"(?i)This rejection records delegated operator review,[^.]+\.\s*", "", text)
    text = re.sub(r"(?i)This review consists of the user's specific correction[^.]+\.\s*", "", text)
    text = re.sub(r"(?i)This rejects attempt\s*\d+ as a scientifically acceptable answer despite its proved formal verdict\.\s*", "", text)
    text = re.sub(r"(?i)No other (?:agent|scientist)'s (?:model|result|proof|code|material|parameter|numerical)[^.;]*(?:supplied|provided)[.;]\s*", "", text)
    text = re.sub(r"(?i)No peer scientist model/code/result is supplied;\s*", "", text)
    text = re.sub(r"(?i)(?:This is a request to revise;\s*)?No acceptance of the current (?:final )?(?:result|recommendation)\.\s*", "", text)
    text = re.sub(r"(?i)This is a request for further work, not acceptance of the complete theorem or final recommendation\.\s*", "", text)
    text = re.sub(r"(?i)This feedback requests revision, not full acceptance of attempt\s*\d+\.\s*", "", text)
    text = re.sub(r"(?i)This is further human feedback, not acceptance of the full result\.\s*", "", text)
    text = re.sub(r"(?i)No (?:scientific |new )?acceptance is given(?: by this response)?\.\s*", "", text)
    text = re.sub(r"(?i)The next candidate (?:still )?requires human review\.\s*", "", text)
    text = re.sub(r"(?i)No revised (?:proof|result) is accepted until (?:the )?human reviews? (?:it)?\.?\s*", "", text)
    text = re.sub(r"(?i)No revised (?:proof|result) is accepted until human review\.\s*", "", text)
    text = re.sub(r"(?i)(?:Retain|Preserve) (?:previous |prior )?attempts(?: and provenance)?[.;]\s*", "", text)
    text = re.sub(r"(?i)Retain prior attempts, human decisions and recovery provenance\.\s*", "", text)
    text = re.sub(r"(?i)This response provides evidence and does not accept any proof\.\s*", "", text)
    text = re.sub(r"(?i)No (?:timing conclusion|acceptance or prescribed optimum) is (?:supplied or approved|given) by this response\.\s*", "", text)
    text = re.sub(r"(?i)This supersedes the temporary wait for more review feedback\.\s*", "", text)
    text = re.sub(r"(?i)Human review is complete;\s*", "", text)
    text = re.sub(r"(?i)User-approved simulated field study:", "Simulated field study:", text)
    text = re.sub(r"(?i)\b(response|request)\s+[a-f0-9]{32,64}\b", r"\1", text)
    for index, quote in enumerate(quotes):
        text = text.replace(f"\ufffcQUOTE{index}\ufffc", quote)
    return re.sub(r"\n{3,}", "\n\n", text).strip()
