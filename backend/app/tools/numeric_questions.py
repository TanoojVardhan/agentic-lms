"""Deterministic numeric questions for the Assessment Agent.

Answers are computed by formula in Python, never by the LLM, so they are
always correct. Values are randomized; pass a seed (for example derived from
a student id) to give each student a different, reproducible set of numbers.
Grading is a plain numeric comparison with an optional tolerance, so it needs
no LLM call.
"""
from __future__ import annotations

import random
from typing import Callable, Dict, List, Optional


def _q(question: str, answer, explanation: str, tag: str, tolerance: float = 0.0) -> Dict:
    return {
        "question": question,
        "options": [],
        "correct_answer": str(answer),
        "bloom_level": "apply",
        "explanation": explanation,
        "question_type": "numeric",
        "tolerance": tolerance,
        "topic_tag": tag,
    }


def _conv_output(r: random.Random) -> Dict:
    while True:
        h = r.choice([28, 32, 64, 96, 128, 224])
        k = r.choice([3, 5, 7])
        s = r.choice([1, 2])
        p = r.choice([0, 1, 2])
        if h - k + 2 * p >= 0 and (h - k + 2 * p) % s == 0:
            break
    out = (h - k + 2 * p) // s + 1
    return _q(
        f"An input of size {h}x{h} passes through a convolution layer with a "
        f"{k}x{k} kernel, stride {s} and padding {p}. What is the height of the "
        f"output feature map?",
        out,
        f"Output = (W - K + 2P) / S + 1 = ({h} - {k} + 2x{p}) / {s} + 1 = {out}.",
        "cnn",
    )


def _conv_params(r: random.Random) -> Dict:
    c = r.choice([1, 3, 16, 32, 64])
    f = r.choice([8, 16, 32, 64])
    k = r.choice([3, 5])
    out = (k * k * c + 1) * f
    return _q(
        f"A convolution layer has {f} filters of size {k}x{k} and receives an "
        f"input with {c} channels. How many trainable parameters does it have "
        f"(including biases)?",
        out,
        f"Params = (K x K x C_in + 1) x filters = ({k}x{k}x{c} + 1) x {f} = {out}.",
        "cnn",
    )


def _pool_output(r: random.Random) -> Dict:
    while True:
        h = r.choice([14, 28, 32, 56, 64, 112])
        pool = r.choice([2, 3])
        s = r.choice([2])
        if (h - pool) % s == 0:
            break
    out = (h - pool) // s + 1
    return _q(
        f"A {h}x{h} feature map goes through max pooling with a {pool}x{pool} "
        f"window and stride {s} (no padding). What is the output height?",
        out,
        f"Output = (W - pool) / S + 1 = ({h} - {pool}) / {s} + 1 = {out}.",
        "cnn",
    )


def _flatten(r: random.Random) -> Dict:
    h = r.choice([4, 5, 7, 8])
    c = r.choice([16, 32, 64, 128])
    out = h * h * c
    return _q(
        f"A feature map of shape {h}x{h}x{c} is flattened before a dense layer. "
        f"How many values does the flattened vector have?",
        out,
        f"Flatten size = H x W x C = {h} x {h} x {c} = {out}.",
        "cnn",
    )


def _dense_params(r: random.Random) -> Dict:
    n = r.choice([64, 128, 256, 784])
    m = r.choice([10, 32, 64, 128])
    out = (n + 1) * m
    return _q(
        f"A dense (fully connected) layer with {m} units receives {n} inputs. "
        f"How many trainable parameters does it have (including biases)?",
        out,
        f"Params = (inputs + 1) x units = ({n} + 1) x {m} = {out}.",
        "dense",
    )


def _rnn_params(r: random.Random) -> Dict:
    d = r.choice([8, 16, 32, 50, 100])
    u = r.choice([16, 32, 64, 128])
    out = u * (u + d + 1)
    return _q(
        f"A simple RNN layer has {u} units and input feature size {d}. How many "
        f"trainable parameters does it have?",
        out,
        f"Params = units x (units + input_dim + 1) = {u} x ({u} + {d} + 1) = {out}.",
        "rnn",
    )


def _lstm_params(r: random.Random) -> Dict:
    d = r.choice([8, 16, 32, 50, 100])
    u = r.choice([16, 32, 64, 128])
    out = 4 * u * (u + d + 1)
    return _q(
        f"An LSTM layer has {u} units and input feature size {d}. How many "
        f"trainable parameters does it have?",
        out,
        f"An LSTM has 4 gates, each like a simple RNN: 4 x units x (units + "
        f"input_dim + 1) = 4 x {u} x ({u} + {d} + 1) = {out}.",
        "rnn",
    )


def _precision(r: random.Random) -> Dict:
    tp = r.randint(30, 90)
    fp = r.randint(5, 30)
    out = round(tp / (tp + fp), 2)
    return _q(
        f"A classifier makes {tp} true positive and {fp} false positive "
        f"predictions. What is its precision? Give the answer to 2 decimal places.",
        f"{out:.2f}",
        f"Precision = TP / (TP + FP) = {tp} / ({tp} + {fp}) = {out:.2f}.",
        "metrics",
        tolerance=0.01,
    )


TEMPLATES: List[Callable[[random.Random], Dict]] = [
    _conv_output, _conv_params, _pool_output, _flatten,
    _dense_params, _rnn_params, _lstm_params, _precision,
]

TOPIC_KEYWORDS = {
    "cnn": ["conv", "cnn", "pool", "filter", "kernel", "stride", "padding", "feature map"],
    "dense": ["dense", "ann", "neural network", "perceptron", "mlp", "fully connected"],
    "rnn": ["rnn", "lstm", "recurrent", "sequence"],
    "metrics": ["precision", "metric", "evaluation", "accuracy"],
}


def generate_numeric(topic: str, num_questions: int, seed: Optional[int] = None) -> List[Dict]:
    """Pick templates matching the topic (all of them if none match)."""
    r = random.Random(seed)
    text = (topic or "").lower()
    tags = {t for t, words in TOPIC_KEYWORDS.items() if any(w in text for w in words)}
    pool = [t for t in TEMPLATES if t(random.Random(0))["topic_tag"] in tags] or TEMPLATES

    order = pool[:]
    r.shuffle(order)
    questions = []
    for i in range(num_questions):
        q = order[i % len(order)](r)
        q.pop("topic_tag", None)
        questions.append(q)
    return questions


def check_numeric(student_answer, correct_answer, tolerance: float = 0.0) -> bool:
    """Compare as numbers; commas and surrounding spaces are ignored."""
    try:
        s = float(str(student_answer).strip().replace(",", ""))
        c = float(str(correct_answer).strip())
    except ValueError:
        return False
    return abs(s - c) <= (tolerance or 0.0) + 1e-9
