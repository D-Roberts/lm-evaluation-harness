"""
Measuring Mathematical Problem Solving With the MATH Dataset
https://arxiv.org/pdf/2103.03874.pdf

Math is a dataset of 12,500 challenging competition mathematics problems. Each
problem in Math has a full step-by-step solution which can be used to teach
models to generate answer derivations and explanations.

Homepage: https://github.com/hendrycks/math
"""
import re
import math
import code
import signal
from abc import ABC

import sympy
from sympy.parsing.latex import parse_latex

import inspect
import lm_eval.datasets.hendrycks_math.hendrycks_math
from lm_eval.metrics import mean
from lm_eval.base import Task, rf
from lm_eval.tasks.math_tasks import SymbolicMathTask


NL_PROMPT=r"""Problem:
Find the domain of the expression  $\frac{\sqrt{x-2}}{\sqrt{5-x}}$.}

Solution:
The expressions inside each square root must be non-negative. Therefore, $x-2 \ge 0$, so $x\ge2$, and $5 - x \ge 0$, so $x \le 5$. Also, the denominator cannot be equal to zero, so $5-x>0$, which gives $x<5$. Therefore, the domain of the expression is $\boxed{[2,5)}$.
Final Answer: The final answer is $[2,5)$. I hope it is correct.

Problem:
If $\det \mathbf{A} = 2$ and $\det \mathbf{B} = 12,$ then find $\det (\mathbf{A} \mathbf{B}).$

Solution:
We have that $\det (\mathbf{A} \mathbf{B}) = (\det \mathbf{A})(\det \mathbf{B}) = (2)(12) = \boxed{24}.$
Final Answer: The final answer is $24$. I hope it is correct.

Problem:
Terrell usually lifts two 20-pound weights 12 times. If he uses two 15-pound weights instead, how many times must Terrell lift them in order to lift the same total weight?

Solution:
If Terrell lifts two 20-pound weights 12 times, he lifts a total of $2\cdot 12\cdot20=480$ pounds of weight.  If he lifts two 15-pound weights instead for $n$ times, he will lift a total of $2\cdot15\cdot n=30n$ pounds of weight.  Equating this to 480 pounds, we can solve for $n$:
\begin{align*}
30n&=480\\
\Rightarrow\qquad n&=480/30=\boxed{16}
\end{align*}
Final Answer: The final answer is $16$. I hope it is correct.

Problem:
If the system of equations

\begin{align*}
6x-4y&=a,\\
6y-9x &=b.
\end{align*}has a solution $(x, y)$ where $x$ and $y$ are both nonzero,
find $\frac{a}{b},$ assuming $b$ is nonzero.

Solution:
If we multiply the first equation by $-\frac{3}{2}$, we obtain

$$6y-9x=-\frac{3}{2}a.$$Since we also know that $6y-9x=b$, we have

$$-\frac{3}{2}a=b\Rightarrow\frac{a}{b}=\boxed{-\frac{2}{3}}.$$
Final Answer: The final answer is $-\frac{2}{3}$. I hope it is correct."""


_CITATION = """
@article{hendrycksmath2021,
  title={Measuring Mathematical Problem Solving With the Math Dataset},
  author={Dan Hendrycks and Collin Burns and Saurav Kadavath and Akul Arora and Steven Basart and Eric Tang and Dawn Song and Jacob Steinhardt},
  journal={NeurIPS},
  year={2021}
}
@misc{lewkowycz2022solving,
      title={Solving Quantitative Reasoning Problems with Language Models}, 
      author={Aitor Lewkowycz and Anders Andreassen and David Dohan and Ethan Dyer and Henryk Michalewski and Vinay Ramasesh and Ambrose Slone and Cem Anil and Imanol Schlag and Theo Gutman-Solo and Yuhuai Wu and Behnam Neyshabur and Guy Gur-Ari and Vedant Misra},
      year={2022},
      eprint={2206.14858},
      archivePrefix={arXiv},
      primaryClass={cs.CL}
}
"""


class MinervaMath(SymbolicMathTask):
    DATASET_PATH = inspect.getfile(lm_eval.datasets.hendrycks_math.hendrycks_math)
    DATASET_NAME = None
    PROMPT = NL_PROMPT

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        print("WARNING: Ignores --num-fewshot argument and uses a fixed prompt")

    def has_training_docs(self):
        return True

    def has_validation_docs(self):
        return False

    def has_test_docs(self):
        return True

    def training_docs(self):
        return map(self._process_doc, self.dataset["train"])

    def validation_docs(self):
        return NotImplemented

    def test_docs(self):
        return map(self._process_doc, self.dataset["test"])

    def fewshot_context(
            self, doc, num_fewshot, provide_description=None, rnd=None, description=None
    ):
        example = self._doc_to_text(doc)
        prompt = self.PROMPT + "\n\n" + example

        return prompt

    @property
    def end_seq(self):
        return "I hope it is correct."

    def get_unnormalized_answer(self, text: str):
        text += self.end_seq
        match = re.search(
                r'Final Answer: The final answer is(.*?). I hope it is correct.',
                text,
        )
        if match: 
            return match.group(1).strip()
        else:
            return self.INVALID_ANSWER

    def _last_boxed_only_string(self, string):

        idx = string.rfind("\\boxed")
        if "\\boxed " in string:
            return "\\boxed " + string.split("\\boxed ")[-1].split("$")[0]
        if idx < 0:
            idx = string.rfind("\\fbox")
            if idx < 0:
                return None

        i = idx
        right_brace_idx = None
        num_left_braces_open = 0
        while i < len(string):
            if string[i] == "{":
                num_left_braces_open += 1
            if string[i] == "}":
                num_left_braces_open -= 1
                if num_left_braces_open == 0:
                    right_brace_idx = i
                    break
            i += 1

        if right_brace_idx is None:
            retval = None
        else:
            retval = string[idx : right_brace_idx + 1]

        return retval

    def _remove_boxed(self, s):
        if "\\boxed " in s:
            left = "\\boxed "
            assert s[: len(left)] == left
            return s[len(left) :]

        left = "\\boxed{"

        assert s[: len(left)] == left
        assert s[-1] == "}"

        return s[len(left) : -1]

    def _process_doc(self, doc):
        doc["answer"] = self.normalize_tex(
                self._remove_boxed(self._last_boxed_only_string(doc["solution"]))
        )
        return doc

    def _doc_to_text(self, doc):
        return "Problem:\n" + doc["problem"] + "\n\nSolution:"
 
class MinervaMathAlgebraEasy(MinervaMath):
    VERSION = 1
    DATASET_NAME = "algebra"

    def training_docs(self):
        data = map(self._process_doc, self.dataset["train"])
        data = filter(lambda x: x['level'] == 'Level 1', data)
        return data

    def test_docs(self):
        data = map(self._process_doc, self.dataset["test"])
        data = filter(lambda x: x['level'] == 'Level 1', data)
        return data


class MinervaMathAlgebra(MinervaMath):
    VERSION = 1
    DATASET_NAME = "algebra"


class MinervaMathCountingAndProbability(MinervaMath):
    VERSION = 1
    DATASET_NAME = "counting_and_probability"


class MinervaMathGeometry(MinervaMath):
    VERSION = 1
    DATASET_NAME = "geometry"


class MinervaMathIntermediateAlgebra(MinervaMath):
    VERSION = 1
    DATASET_NAME = "intermediate_algebra"


class MinervaMathNumberTheory(MinervaMath):
    VERSION = 1
    DATASET_NAME = "number_theory"


class MinervaMathPrealgebra(MinervaMath):
    VERSION = 1
    DATASET_NAME = "prealgebra"


class MinervaMathPrecalculus(MinervaMath):
    VERSION = 1
    DATASET_NAME = "precalculus"
