"""A curated, PRE-REGISTERED bank of firewalled coding problems — breadth for the coding claims.

Each problem carries DEV tests (the agent's gate) and HELD-OUT tests (the oracle's grade) on DISJOINT
inputs, so a candidate overfit to the dev inputs fails the held-out grade (the firewall). The set spans
string ops, parsing, search, and small algorithms — enough breadth that "orchestration reaches the
strong model" is a claim about coding, not about one lucky task. The bank is committed (git-timestamped
= the pre-registration); `tests/test_coding_problems.py` verifies every problem is solvable and the
firewall is fair by running a reference solution through both gates.
"""

from __future__ import annotations

from .coding import CodingProblem

_GATE = "ruff check . && mypy --strict . && python -m pytest -q"


def _p(pid: str, module: str, signature: str, desc: str, dev: str, grade: str) -> CodingProblem:
    spec = (
        f"Write `{signature}` in {module}.py: {desc} Output ONLY a `# path: {module}.py` line then a "
        f"fenced ```python block. Fully type-annotated; add no unused import; must pass mypy --strict."
    )
    return CodingProblem(
        problem_id=pid,
        spec=spec,
        dev_gate=_GATE,
        dev_fixtures={"test_dev.py": dev},
        grading_command=_GATE,
        grading_tests={"test_grade.py": grade},
    )


def coding_problem_bank() -> list[CodingProblem]:
    """The frozen problem set (pre-registered). Disjoint dev/held-out tests per problem."""
    return [
        _p(
            "rle",
            "rle",
            "def run_length_encode(s: str) -> list[tuple[str, int]]",
            "run-length encode: consecutive equal chars grouped as (char, count), in order.",
            "from rle import run_length_encode\n\n\n"
            "def test_a() -> None:\n    assert run_length_encode('aaabbc') == [('a', 3), ('b', 2), ('c', 1)]\n\n\n"
            "def test_empty() -> None:\n    assert run_length_encode('') == []\n",
            "from rle import run_length_encode\n\n\n"
            "def test_mixed() -> None:\n    assert run_length_encode('xxyz') == [('x', 2), ('y', 1), ('z', 1)]\n\n\n"
            "def test_single() -> None:\n    assert run_length_encode('q') == [('q', 1)]\n\n\n"
            "def test_pair() -> None:\n    assert run_length_encode('zz') == [('z', 2)]\n",
        ),
        _p(
            "duration",
            "duration",
            "def parse_duration(s: str) -> int",
            "parse a duration like '1h30m' into total seconds (h=3600, m=60, s=1; components combine).",
            "from duration import parse_duration\n\n\n"
            "def test_hm() -> None:\n    assert parse_duration('1h30m') == 5400\n\n\n"
            "def test_s() -> None:\n    assert parse_duration('45s') == 45\n",
            "from duration import parse_duration\n\n\n"
            "def test_h() -> None:\n    assert parse_duration('2h') == 7200\n\n\n"
            "def test_m() -> None:\n    assert parse_duration('90m') == 5400\n\n\n"
            "def test_hms() -> None:\n    assert parse_duration('3h15m') == 11700\n",
        ),
        _p(
            "reverse_words",
            "rw",
            "def reverse_words(s: str) -> str",
            "reverse the order of whitespace-separated words, joined by single spaces.",
            "from rw import reverse_words\n\n\n"
            "def test_two() -> None:\n    assert reverse_words('hello world') == 'world hello'\n\n\n"
            "def test_three() -> None:\n    assert reverse_words('a b c') == 'c b a'\n",
            "from rw import reverse_words\n\n\n"
            "def test_long() -> None:\n    assert reverse_words('one two three') == 'three two one'\n\n\n"
            "def test_one() -> None:\n    assert reverse_words('x') == 'x'\n\n\n"
            "def test_pair() -> None:\n    assert reverse_words('foo bar') == 'bar foo'\n",
        ),
        _p(
            "balanced",
            "bal",
            "def is_balanced(s: str) -> bool",
            "True iff (), [], {} are balanced and correctly nested; ignore other chars.",
            "from bal import is_balanced\n\n\n"
            "def test_ok() -> None:\n    assert is_balanced('(a[b]{c})') is True\n\n\n"
            "def test_bad() -> None:\n    assert is_balanced('(]') is False\n",
            "from bal import is_balanced\n\n\n"
            "def test_simple() -> None:\n    assert is_balanced('[]') is True\n\n\n"
            "def test_crossed() -> None:\n    assert is_balanced('([)]') is False\n\n\n"
            "def test_unclosed() -> None:\n    assert is_balanced('(((') is False\n\n\n"
            "def test_empty() -> None:\n    assert is_balanced('') is True\n",
        ),
        _p(
            "two_sum",
            "ts",
            "def two_sum(nums: list[int], target: int) -> tuple[int, int]",
            "return the indices (i, j) of the first pair summing to target (i<j); (-1, -1) if none.",
            "from ts import two_sum\n\n\n"
            "def test_basic() -> None:\n    assert two_sum([2, 7, 11], 9) == (0, 1)\n\n\n"
            "def test_dup() -> None:\n    assert two_sum([3, 3], 6) == (0, 1)\n",
            "from ts import two_sum\n\n\n"
            "def test_end() -> None:\n    assert two_sum([1, 2, 3, 4], 7) == (2, 3)\n\n\n"
            "def test_first() -> None:\n    assert two_sum([5, 1], 6) == (0, 1)\n\n\n"
            "def test_mid() -> None:\n    assert two_sum([0, 4, 3], 7) == (1, 2)\n",
        ),
        _p(
            "roman",
            "rom",
            "def roman_to_int(s: str) -> int",
            "convert a Roman numeral string to its integer value (subtractive notation).",
            "from rom import roman_to_int\n\n\n"
            "def test_iii() -> None:\n    assert roman_to_int('III') == 3\n\n\n"
            "def test_iv() -> None:\n    assert roman_to_int('IV') == 4\n",
            "from rom import roman_to_int\n\n\n"
            "def test_ix() -> None:\n    assert roman_to_int('IX') == 9\n\n\n"
            "def test_lviii() -> None:\n    assert roman_to_int('LVIII') == 58\n\n\n"
            "def test_big() -> None:\n    assert roman_to_int('MCMXCIV') == 1994\n",
        ),
        _p(
            "fizzbuzz",
            "fb",
            "def fizzbuzz(n: int) -> list[str]",
            "1..n as strings; multiples of 3 -> 'Fizz', of 5 -> 'Buzz', of both -> 'FizzBuzz'.",
            "from fb import fizzbuzz\n\n\n"
            "def test_three() -> None:\n    assert fizzbuzz(3) == ['1', '2', 'Fizz']\n\n\n"
            "def test_five() -> None:\n    assert fizzbuzz(5) == ['1', '2', 'Fizz', '4', 'Buzz']\n",
            "from fb import fizzbuzz\n\n\n"
            "def test_one() -> None:\n    assert fizzbuzz(1) == ['1']\n\n\n"
            "def test_fifteen() -> None:\n    assert fizzbuzz(15)[-1] == 'FizzBuzz'\n\n\n"
            "def test_six() -> None:\n    assert fizzbuzz(6) == ['1', '2', 'Fizz', '4', 'Buzz', 'Fizz']\n",
        ),
        _p(
            "caesar",
            "caes",
            "def caesar(s: str, shift: int) -> str",
            "shift lowercase letters by `shift` (wrapping a..z); leave other characters unchanged.",
            "from caes import caesar\n\n\n"
            "def test_abc() -> None:\n    assert caesar('abc', 1) == 'bcd'\n\n\n"
            "def test_wrap() -> None:\n    assert caesar('xyz', 3) == 'abc'\n",
            "from caes import caesar\n\n\n"
            "def test_word() -> None:\n    assert caesar('hello', 1) == 'ifmmp'\n\n\n"
            "def test_a() -> None:\n    assert caesar('a', 25) == 'z'\n\n\n"
            "def test_z() -> None:\n    assert caesar('z', 1) == 'a'\n",
        ),
        _p(
            "bsearch",
            "bs",
            "def binary_search(xs: list[int], target: int) -> int",
            "return the index of target in the sorted list xs, or -1 if absent.",
            "from bs import binary_search\n\n\n"
            "def test_found() -> None:\n    assert binary_search([1, 3, 5, 7], 5) == 2\n\n\n"
            "def test_absent() -> None:\n    assert binary_search([1, 3, 5, 7], 4) == -1\n",
            "from bs import binary_search\n\n\n"
            "def test_first() -> None:\n    assert binary_search([1, 2, 3], 1) == 0\n\n\n"
            "def test_last() -> None:\n    assert binary_search([1, 2, 3], 3) == 2\n\n\n"
            "def test_empty() -> None:\n    assert binary_search([], 1) == -1\n\n\n"
            "def test_mid() -> None:\n    assert binary_search([2, 4, 6, 8, 10], 8) == 3\n",
        ),
        _p(
            "word_count",
            "wc",
            "def word_count(s: str) -> dict[str, int]",
            "count occurrences of each whitespace-separated word; empty string -> empty dict.",
            "from wc import word_count\n\n\n"
            "def test_repeat() -> None:\n    assert word_count('a b a') == {'a': 2, 'b': 1}\n\n\n"
            "def test_empty() -> None:\n    assert word_count('') == {}\n",
            "from wc import word_count\n\n\n"
            "def test_distinct() -> None:\n    assert word_count('x y z') == {'x': 1, 'y': 1, 'z': 1}\n\n\n"
            "def test_triple() -> None:\n    assert word_count('foo foo foo') == {'foo': 3}\n\n\n"
            "def test_one() -> None:\n    assert word_count('one') == {'one': 1}\n",
        ),
        # ── numbers (agent-authored, gate-verified) ──
        _p(
            "gcd",
            "gd",
            "def gcd(a: int, b: int) -> int",
            "greatest common divisor of two non-negative ints (gcd(a, 0) == a).",
            "from gd import gcd\n\n\ndef test_basic() -> None:\n    assert gcd(12, 8) == 4\n\n\n"
            "def test_zero() -> None:\n    assert gcd(5, 0) == 5\n",
            "from gd import gcd\n\n\ndef test_coprime() -> None:\n    assert gcd(7, 13) == 1\n\n\n"
            "def test_equal() -> None:\n    assert gcd(9, 9) == 9\n\n\n"
            "def test_mult() -> None:\n    assert gcd(100, 60) == 20\n",
        ),
        _p(
            "lcm",
            "lc",
            "def lcm(a: int, b: int) -> int",
            "least common multiple of two positive ints (a // gcd(a, b) * b).",
            "from lc import lcm\n\n\ndef test_basic() -> None:\n    assert lcm(4, 6) == 12\n\n\n"
            "def test_coprime() -> None:\n    assert lcm(3, 5) == 15\n",
            "from lc import lcm\n\n\ndef test_div() -> None:\n    assert lcm(2, 8) == 8\n\n\n"
            "def test_equal() -> None:\n    assert lcm(7, 7) == 7\n\n\n"
            "def test_big() -> None:\n    assert lcm(12, 18) == 36\n",
        ),
        _p(
            "is_prime",
            "pr",
            "def is_prime(n: int) -> bool",
            "True iff n is a prime number (n < 2 is not prime).",
            "from pr import is_prime\n\n\ndef test_prime() -> None:\n    assert is_prime(7) is True\n\n\n"
            "def test_one() -> None:\n    assert is_prime(1) is False\n",
            "from pr import is_prime\n\n\ndef test_two() -> None:\n    assert is_prime(2) is True\n\n\n"
            "def test_nine() -> None:\n    assert is_prime(9) is False\n\n\n"
            "def test_thirteen() -> None:\n    assert is_prime(13) is True\n\n\n"
            "def test_zero() -> None:\n    assert is_prime(0) is False\n",
        ),
        _p(
            "factorial",
            "fac",
            "def factorial(n: int) -> int",
            "factorial of a non-negative int n (factorial(0) == 1).",
            "from fac import factorial\n\n\ndef test_five() -> None:\n    assert factorial(5) == 120\n\n\n"
            "def test_zero() -> None:\n    assert factorial(0) == 1\n",
            "from fac import factorial\n\n\ndef test_one() -> None:\n    assert factorial(1) == 1\n\n\n"
            "def test_three() -> None:\n    assert factorial(3) == 6\n\n\n"
            "def test_six() -> None:\n    assert factorial(6) == 720\n",
        ),
        _p(
            "digit_sum",
            "ds",
            "def digit_sum(n: int) -> int",
            "sum of the decimal digits of a non-negative int (digit_sum(0) == 0).",
            "from ds import digit_sum\n\n\ndef test_basic() -> None:\n    assert digit_sum(123) == 6\n\n\n"
            "def test_zero() -> None:\n    assert digit_sum(0) == 0\n",
            "from ds import digit_sum\n\n\ndef test_nines() -> None:\n    assert digit_sum(99) == 18\n\n\n"
            "def test_thousand() -> None:\n    assert digit_sum(1000) == 1\n\n\n"
            "def test_mixed() -> None:\n    assert digit_sum(456) == 15\n",
        ),
        _p(
            "sum_of_divisors",
            "sd",
            "def sum_of_divisors(n: int) -> int",
            "sum of all positive divisors of n, including 1 and n itself.",
            "from sd import sum_of_divisors\n\n\ndef test_six() -> None:\n    assert sum_of_divisors(6) == 12\n\n\n"
            "def test_one() -> None:\n    assert sum_of_divisors(1) == 1\n",
            "from sd import sum_of_divisors\n\n\ndef test_twelve() -> None:\n    assert sum_of_divisors(12) == 28\n\n\n"
            "def test_prime() -> None:\n    assert sum_of_divisors(7) == 8\n\n\n"
            "def test_perfect() -> None:\n    assert sum_of_divisors(28) == 56\n",
        ),
        _p(
            "is_perfect",
            "pf",
            "def is_perfect(n: int) -> bool",
            "True iff n equals the sum of its proper divisors (e.g. 6 = 1+2+3).",
            "from pf import is_perfect\n\n\ndef test_six() -> None:\n    assert is_perfect(6) is True\n\n\n"
            "def test_eight() -> None:\n    assert is_perfect(8) is False\n",
            "from pf import is_perfect\n\n\ndef test_28() -> None:\n    assert is_perfect(28) is True\n\n\n"
            "def test_12() -> None:\n    assert is_perfect(12) is False\n\n\n"
            "def test_496() -> None:\n    assert is_perfect(496) is True\n\n\n"
            "def test_one() -> None:\n    assert is_perfect(1) is False\n",
        ),
        _p(
            "collatz_steps",
            "col",
            "def collatz_steps(n: int) -> int",
            "number of Collatz steps to reach 1 (even -> n//2, odd -> 3n+1); collatz_steps(1) == 0.",
            "from col import collatz_steps\n\n\ndef test_one() -> None:\n    assert collatz_steps(1) == 0\n\n\n"
            "def test_three() -> None:\n    assert collatz_steps(3) == 7\n",
            "from col import collatz_steps\n\n\ndef test_four() -> None:\n    assert collatz_steps(4) == 2\n\n\n"
            "def test_six() -> None:\n    assert collatz_steps(6) == 8\n\n\n"
            "def test_seven() -> None:\n    assert collatz_steps(7) == 16\n",
        ),
        _p(
            "nth_fibonacci",
            "fib",
            "def nth_fibonacci(n: int) -> int",
            "the nth Fibonacci number, 0-indexed (fib(0) == 0, fib(1) == 1).",
            "from fib import nth_fibonacci\n\n\ndef test_zero() -> None:\n    assert nth_fibonacci(0) == 0\n\n\n"
            "def test_seven() -> None:\n    assert nth_fibonacci(7) == 13\n",
            "from fib import nth_fibonacci\n\n\ndef test_one() -> None:\n    assert nth_fibonacci(1) == 1\n\n\n"
            "def test_ten() -> None:\n    assert nth_fibonacci(10) == 55\n\n\n"
            "def test_two() -> None:\n    assert nth_fibonacci(2) == 1\n\n\n"
            "def test_twelve() -> None:\n    assert nth_fibonacci(12) == 144\n",
        ),
        _p(
            "count_set_bits",
            "csb",
            "def count_set_bits(n: int) -> int",
            "number of 1-bits in the binary representation of a non-negative int.",
            "from csb import count_set_bits\n\n\ndef test_seven() -> None:\n    assert count_set_bits(7) == 3\n\n\n"
            "def test_zero() -> None:\n    assert count_set_bits(0) == 0\n",
            "from csb import count_set_bits\n\n\ndef test_eight() -> None:\n    assert count_set_bits(8) == 1\n\n\n"
            "def test_255() -> None:\n    assert count_set_bits(255) == 8\n\n\n"
            "def test_1023() -> None:\n    assert count_set_bits(1023) == 10\n",
        ),
        _p(
            "reverse_integer",
            "ri",
            "def reverse_integer(n: int) -> int",
            "reverse the decimal digits of n, preserving sign (reverse_integer(-120) == -21).",
            "from ri import reverse_integer\n\n\ndef test_basic() -> None:\n    assert reverse_integer(123) == 321\n\n\n"
            "def test_neg() -> None:\n    assert reverse_integer(-45) == -54\n",
            "from ri import reverse_integer\n\n\ndef test_trailing() -> None:\n    assert reverse_integer(100) == 1\n\n\n"
            "def test_single() -> None:\n    assert reverse_integer(7) == 7\n\n\n"
            "def test_neg_trailing() -> None:\n    assert reverse_integer(-120) == -21\n\n\n"
            "def test_zero() -> None:\n    assert reverse_integer(0) == 0\n",
        ),
        _p(
            "is_armstrong",
            "arm",
            "def is_armstrong(n: int) -> bool",
            "True iff n equals the sum of its digits each raised to the digit-count power (e.g. 153).",
            "from arm import is_armstrong\n\n\ndef test_153() -> None:\n    assert is_armstrong(153) is True\n\n\n"
            "def test_ten() -> None:\n    assert is_armstrong(10) is False\n",
            "from arm import is_armstrong\n\n\ndef test_nine() -> None:\n    assert is_armstrong(9) is True\n\n\n"
            "def test_370() -> None:\n    assert is_armstrong(370) is True\n\n\n"
            "def test_100() -> None:\n    assert is_armstrong(100) is False\n\n\n"
            "def test_407() -> None:\n    assert is_armstrong(407) is True\n",
        ),
        _p(
            "sum_even",
            "se",
            "def sum_even(n: int) -> int",
            "sum of the even integers from 1 to n inclusive (sum_even(1) == 0).",
            "from se import sum_even\n\n\ndef test_ten() -> None:\n    assert sum_even(10) == 30\n\n\n"
            "def test_one() -> None:\n    assert sum_even(1) == 0\n",
            "from se import sum_even\n\n\ndef test_two() -> None:\n    assert sum_even(2) == 2\n\n\n"
            "def test_five() -> None:\n    assert sum_even(5) == 6\n\n\n"
            "def test_hundred() -> None:\n    assert sum_even(100) == 2550\n\n\n"
            "def test_zero() -> None:\n    assert sum_even(0) == 0\n",
        ),
        # ── strings ──
        _p(
            "pal",
            "pal",
            "def is_palindrome(s: str) -> bool",
            "True iff s reads the same forwards and backwards considering only alphanumeric chars, case-insensitive.",
            "from pal import is_palindrome\n\n\ndef test_phrase() -> None:\n    assert is_palindrome('A man, a plan, a canal: Panama') is True\n\n\ndef test_no() -> None:\n    assert is_palindrome('hello') is False\n",
            "from pal import is_palindrome\n\n\ndef test_simple() -> None:\n    assert is_palindrome('racecar') is True\n\n\ndef test_cat() -> None:\n    assert is_palindrome('Was it a car or a cat I saw?') is True\n\n\ndef test_two() -> None:\n    assert is_palindrome('ab') is False\n\n\ndef test_empty() -> None:\n    assert is_palindrome('') is True\n",
        ),
        _p(
            "anagram",
            "anagram",
            "def are_anagrams(a: str, b: str) -> bool",
            "True iff a and b are anagrams, ignoring case and whitespace.",
            "from anagram import are_anagrams\n\n\ndef test_yes() -> None:\n    assert are_anagrams('listen', 'silent') is True\n\n\ndef test_no() -> None:\n    assert are_anagrams('foo', 'bar') is False\n",
            "from anagram import are_anagrams\n\n\ndef test_phrase() -> None:\n    assert are_anagrams('Dormitory', 'Dirty Room') is True\n\n\ndef test_len() -> None:\n    assert are_anagrams('a', 'aa') is False\n\n\ndef test_tales() -> None:\n    assert are_anagrams('rail safety', 'fairy tales') is True\n",
        ),
        _p(
            "vowels",
            "vowels",
            "def count_vowels(s: str) -> int",
            "count the vowels (a, e, i, o, u) in s, case-insensitive.",
            "from vowels import count_vowels\n\n\ndef test_word() -> None:\n    assert count_vowels('hello') == 2\n\n\ndef test_none() -> None:\n    assert count_vowels('xyz') == 0\n",
            "from vowels import count_vowels\n\n\ndef test_all() -> None:\n    assert count_vowels('AEIOU') == 5\n\n\ndef test_mixed() -> None:\n    assert count_vowels('Programming') == 3\n\n\ndef test_empty() -> None:\n    assert count_vowels('') == 0\n",
        ),
        _p(
            "lcp",
            "lcp",
            "def longest_common_prefix(strs: list[str]) -> str",
            "return the longest common prefix of all strings; '' if none or list empty.",
            "from lcp import longest_common_prefix\n\n\ndef test_flow() -> None:\n    assert longest_common_prefix(['flower', 'flow', 'flight']) == 'fl'\n\n\ndef test_none() -> None:\n    assert longest_common_prefix(['dog', 'cat']) == ''\n",
            "from lcp import longest_common_prefix\n\n\ndef test_inter() -> None:\n    assert longest_common_prefix(['interspecies', 'interstellar', 'interstate']) == 'inters'\n\n\ndef test_one() -> None:\n    assert longest_common_prefix(['abc']) == 'abc'\n\n\ndef test_empty() -> None:\n    assert longest_common_prefix([]) == ''\n\n\ndef test_short() -> None:\n    assert longest_common_prefix(['a', 'ab']) == 'a'\n",
        ),
        _p(
            "occur",
            "occur",
            "def count_occurrences(s: str, sub: str) -> int",
            "count non-overlapping occurrences of sub in s.",
            "from occur import count_occurrences\n\n\ndef test_banana() -> None:\n    assert count_occurrences('banana', 'a') == 3\n\n\ndef test_overlap() -> None:\n    assert count_occurrences('aaaa', 'aa') == 2\n",
            "from occur import count_occurrences\n\n\ndef test_o() -> None:\n    assert count_occurrences('hello world', 'o') == 2\n\n\ndef test_abc() -> None:\n    assert count_occurrences('abcabc', 'abc') == 2\n\n\ndef test_ss() -> None:\n    assert count_occurrences('mississippi', 'ss') == 2\n\n\ndef test_absent() -> None:\n    assert count_occurrences('xyz', 'a') == 0\n",
        ),
        _p(
            "dedup",
            "dedup",
            "def remove_duplicate_chars(s: str) -> str",
            "remove duplicate characters, keeping the first occurrence of each in order.",
            "from dedup import remove_duplicate_chars\n\n\ndef test_banana() -> None:\n    assert remove_duplicate_chars('banana') == 'ban'\n\n\ndef test_clean() -> None:\n    assert remove_duplicate_chars('abc') == 'abc'\n",
            "from dedup import remove_duplicate_chars\n\n\ndef test_pairs() -> None:\n    assert remove_duplicate_chars('aabbcc') == 'abc'\n\n\ndef test_miss() -> None:\n    assert remove_duplicate_chars('mississippi') == 'misp'\n\n\ndef test_empty() -> None:\n    assert remove_duplicate_chars('') == ''\n\n\ndef test_case() -> None:\n    assert remove_duplicate_chars('aAaA') == 'aA'\n",
        ),
        _p(
            "snake",
            "snake",
            "def to_snake_case(s: str) -> str",
            "convert camelCase/PascalCase to snake_case: lowercase each uppercase letter, prefixing '_' unless at index 0.",
            "from snake import to_snake_case\n\n\ndef test_camel() -> None:\n    assert to_snake_case('camelCase') == 'camel_case'\n\n\ndef test_hello() -> None:\n    assert to_snake_case('helloWorld') == 'hello_world'\n",
            "from snake import to_snake_case\n\n\ndef test_pascal() -> None:\n    assert to_snake_case('PascalCase') == 'pascal_case'\n\n\ndef test_three() -> None:\n    assert to_snake_case('myVariableName') == 'my_variable_name'\n\n\ndef test_plain() -> None:\n    assert to_snake_case('word') == 'word'\n",
        ),
        _p(
            "capwords",
            "capwords",
            "def capitalize_words(s: str) -> str",
            "title-case each whitespace-separated word (first letter upper, rest lower), joined by single spaces.",
            "from capwords import capitalize_words\n\n\ndef test_two() -> None:\n    assert capitalize_words('hello world') == 'Hello World'\n\n\ndef test_mixed() -> None:\n    assert capitalize_words('the QUICK fox') == 'The Quick Fox'\n",
            "from capwords import capitalize_words\n\n\ndef test_singles() -> None:\n    assert capitalize_words('a b c') == 'A B C'\n\n\ndef test_upper() -> None:\n    assert capitalize_words('PYTHON programming') == 'Python Programming'\n\n\ndef test_one() -> None:\n    assert capitalize_words('single') == 'Single'\n",
        ),
        _p(
            "freq",
            "freq",
            "def char_frequency_sorted(s: str) -> list[tuple[str, int]]",
            "character frequencies as (char, count), sorted by count descending then char ascending.",
            "from freq import char_frequency_sorted\n\n\ndef test_basic() -> None:\n    assert char_frequency_sorted('aaabb') == [('a', 3), ('b', 2)]\n\n\ndef test_tie() -> None:\n    assert char_frequency_sorted('abc') == [('a', 1), ('b', 1), ('c', 1)]\n",
            "from freq import char_frequency_sorted\n\n\ndef test_banana() -> None:\n    assert char_frequency_sorted('banana') == [('a', 3), ('n', 2), ('b', 1)]\n\n\ndef test_single() -> None:\n    assert char_frequency_sorted('zzz') == [('z', 3)]\n\n\ndef test_empty() -> None:\n    assert char_frequency_sorted('') == []\n\n\ndef test_order() -> None:\n    assert char_frequency_sorted('cba') == [('a', 1), ('b', 1), ('c', 1)]\n",
        ),
        _p(
            "firstuniq",
            "firstuniq",
            "def first_unique_char(s: str) -> int",
            "index of the first non-repeating character in s, or -1 if none.",
            "from firstuniq import first_unique_char\n\n\ndef test_first() -> None:\n    assert first_unique_char('leetcode') == 0\n\n\ndef test_none() -> None:\n    assert first_unique_char('aabb') == -1\n",
            "from firstuniq import first_unique_char\n\n\ndef test_mid() -> None:\n    assert first_unique_char('loveleetcode') == 2\n\n\ndef test_last() -> None:\n    assert first_unique_char('aabbc') == 4\n\n\ndef test_empty() -> None:\n    assert first_unique_char('') == -1\n\n\ndef test_one() -> None:\n    assert first_unique_char('x') == 0\n",
        ),
        _p(
            "strippunc",
            "strippunc",
            "def strip_punctuation(s: str) -> str",
            "remove all ASCII punctuation characters (string.punctuation), keeping everything else.",
            "from strippunc import strip_punctuation\n\n\ndef test_comma() -> None:\n    assert strip_punctuation('hello, world!') == 'hello world'\n\n\ndef test_dots() -> None:\n    assert strip_punctuation('a.b.c') == 'abc'\n",
            "from strippunc import strip_punctuation\n\n\ndef test_apos() -> None:\n    assert strip_punctuation(\"it's a test.\") == 'its a test'\n\n\ndef test_only() -> None:\n    assert strip_punctuation('!!!') == ''\n\n\ndef test_dash() -> None:\n    assert strip_punctuation('no-punct here') == 'nopunct here'\n\n\ndef test_digits() -> None:\n    assert strip_punctuation('123') == '123'\n",
        ),
        _p(
            "mostchar",
            "mostchar",
            "def most_common_char(s: str) -> str",
            "the most frequent character; on ties the one appearing earliest; '' for empty input.",
            "from mostchar import most_common_char\n\n\ndef test_b() -> None:\n    assert most_common_char('aabbbc') == 'b'\n\n\ndef test_first() -> None:\n    assert most_common_char('xyz') == 'x'\n",
            "from mostchar import most_common_char\n\n\ndef test_tie() -> None:\n    assert most_common_char('mississippi') == 'i'\n\n\ndef test_all() -> None:\n    assert most_common_char('aaa') == 'a'\n\n\ndef test_empty() -> None:\n    assert most_common_char('') == ''\n\n\ndef test_early() -> None:\n    assert most_common_char('abcabc') == 'a'\n",
        ),
        # ── lists / dicts ──
        _p(
            "flatten_one_level",
            "fl",
            "def flatten_one_level(xss: list[list[int]]) -> list[int]",
            "concatenate the sublists of `xss` into a single flat list, left to right (one level only).",
            "from fl import flatten_one_level\n\n\ndef test_basic() -> None:\n    assert flatten_one_level([[1, 2], [3], [4, 5]]) == [1, 2, 3, 4, 5]\n\n\ndef test_empties() -> None:\n    assert flatten_one_level([[], [1], []]) == [1]\n",
            "from fl import flatten_one_level\n\n\ndef test_single() -> None:\n    assert flatten_one_level([[7, 8, 9]]) == [7, 8, 9]\n\n\ndef test_none() -> None:\n    assert flatten_one_level([]) == []\n\n\ndef test_negs() -> None:\n    assert flatten_one_level([[-1], [0, -2]]) == [-1, 0, -2]\n",
        ),
        _p(
            "dedup_preserve_order",
            "dpo",
            "def dedup_preserve_order(xs: list[int]) -> list[int]",
            "return xs with duplicates removed, keeping the first occurrence of each value in original order.",
            "from dpo import dedup_preserve_order\n\n\ndef test_dups() -> None:\n    assert dedup_preserve_order([1, 2, 1, 3, 2]) == [1, 2, 3]\n\n\ndef test_clean() -> None:\n    assert dedup_preserve_order([4, 5, 6]) == [4, 5, 6]\n",
            "from dpo import dedup_preserve_order\n\n\ndef test_all_same() -> None:\n    assert dedup_preserve_order([9, 9, 9]) == [9]\n\n\ndef test_empty() -> None:\n    assert dedup_preserve_order([]) == []\n\n\ndef test_order() -> None:\n    assert dedup_preserve_order([3, 1, 3, 2, 1]) == [3, 1, 2]\n",
        ),
        _p(
            "rotate_left",
            "rl",
            "def rotate_left(xs: list[int], k: int) -> list[int]",
            "return xs rotated left by k positions; k>=0 and may exceed len(xs) (rotate by k mod len).",
            "from rl import rotate_left\n\n\ndef test_basic() -> None:\n    assert rotate_left([1, 2, 3, 4], 1) == [2, 3, 4, 1]\n\n\ndef test_wrap() -> None:\n    assert rotate_left([1, 2, 3], 4) == [2, 3, 1]\n",
            "from rl import rotate_left\n\n\ndef test_zero() -> None:\n    assert rotate_left([1, 2, 3], 0) == [1, 2, 3]\n\n\ndef test_full() -> None:\n    assert rotate_left([5, 6], 2) == [5, 6]\n\n\ndef test_empty() -> None:\n    assert rotate_left([], 3) == []\n",
        ),
        _p(
            "running_max",
            "rmax",
            "def running_max(xs: list[int]) -> list[int]",
            "return the list whose i-th element is max(xs[0..i]); empty input yields empty output.",
            "from rmax import running_max\n\n\ndef test_basic() -> None:\n    assert running_max([1, 3, 2, 5, 4]) == [1, 3, 3, 5, 5]\n\n\ndef test_desc() -> None:\n    assert running_max([5, 4, 3]) == [5, 5, 5]\n",
            "from rmax import running_max\n\n\ndef test_negs() -> None:\n    assert running_max([-3, -5, -1]) == [-3, -3, -1]\n\n\ndef test_single() -> None:\n    assert running_max([7]) == [7]\n\n\ndef test_empty() -> None:\n    assert running_max([]) == []\n",
        ),
        _p(
            "most_common_element",
            "mce",
            "def most_common_element(xs: list[int]) -> int",
            "return the value with the highest count in xs; on ties return the one appearing first. xs is non-empty.",
            "from mce import most_common_element\n\n\ndef test_basic() -> None:\n    assert most_common_element([1, 2, 2, 3, 2]) == 2\n\n\ndef test_tie() -> None:\n    assert most_common_element([5, 4, 5, 4]) == 5\n",
            "from mce import most_common_element\n\n\ndef test_single() -> None:\n    assert most_common_element([9]) == 9\n\n\ndef test_late() -> None:\n    assert most_common_element([1, 2, 3, 3]) == 3\n\n\ndef test_tie_first() -> None:\n    assert most_common_element([7, 8, 8, 7]) == 7\n",
        ),
        _p(
            "transpose",
            "tr",
            "def transpose(matrix: list[list[int]]) -> list[list[int]]",
            "return the transpose of a rectangular matrix (rows become columns); empty input yields empty list.",
            "from tr import transpose\n\n\ndef test_rect() -> None:\n    assert transpose([[1, 2, 3], [4, 5, 6]]) == [[1, 4], [2, 5], [3, 6]]\n\n\ndef test_square() -> None:\n    assert transpose([[1, 2], [3, 4]]) == [[1, 3], [2, 4]]\n",
            "from tr import transpose\n\n\ndef test_single_row() -> None:\n    assert transpose([[1, 2, 3]]) == [[1], [2], [3]]\n\n\ndef test_single_col() -> None:\n    assert transpose([[1], [2]]) == [[1, 2]]\n\n\ndef test_empty() -> None:\n    assert transpose([]) == []\n",
        ),
        _p(
            "merge_dicts_summing_values",
            "mds",
            "def merge_dicts_summing_values(a: dict[str, int], b: dict[str, int]) -> dict[str, int]",
            "merge a and b; for keys in both, the value is the sum; keys unique to either are kept as-is.",
            "from mds import merge_dicts_summing_values\n\n\ndef test_overlap() -> None:\n    assert merge_dicts_summing_values({'a': 1, 'b': 2}, {'b': 3, 'c': 4}) == {'a': 1, 'b': 5, 'c': 4}\n\n\ndef test_disjoint() -> None:\n    assert merge_dicts_summing_values({'x': 1}, {'y': 2}) == {'x': 1, 'y': 2}\n",
            "from mds import merge_dicts_summing_values\n\n\ndef test_empty_b() -> None:\n    assert merge_dicts_summing_values({'a': 5}, {}) == {'a': 5}\n\n\ndef test_empty_a() -> None:\n    assert merge_dicts_summing_values({}, {'z': 7}) == {'z': 7}\n\n\ndef test_negs() -> None:\n    assert merge_dicts_summing_values({'a': 2}, {'a': -2}) == {'a': 0}\n",
        ),
        _p(
            "invert_dict",
            "inv",
            "def invert_dict(d: dict[str, int]) -> dict[int, str]",
            "return a new dict mapping each value back to its key; values in d are assumed unique.",
            "from inv import invert_dict\n\n\ndef test_basic() -> None:\n    assert invert_dict({'a': 1, 'b': 2}) == {1: 'a', 2: 'b'}\n\n\ndef test_empty() -> None:\n    assert invert_dict({}) == {}\n",
            "from inv import invert_dict\n\n\ndef test_single() -> None:\n    assert invert_dict({'x': 9}) == {9: 'x'}\n\n\ndef test_three() -> None:\n    assert invert_dict({'p': 10, 'q': 20, 'r': 30}) == {10: 'p', 20: 'q', 30: 'r'}\n\n\ndef test_neg_val() -> None:\n    assert invert_dict({'n': -1}) == {-1: 'n'}\n",
        ),
        _p(
            "group_by_parity",
            "gbp",
            "def group_by_parity(xs: list[int]) -> dict[str, list[int]]",
            "return {'even': [...], 'odd': [...]} partitioning xs by parity, preserving order; both keys always present.",
            "from gbp import group_by_parity\n\n\ndef test_basic() -> None:\n    assert group_by_parity([1, 2, 3, 4]) == {'even': [2, 4], 'odd': [1, 3]}\n\n\ndef test_all_even() -> None:\n    assert group_by_parity([2, 4]) == {'even': [2, 4], 'odd': []}\n",
            "from gbp import group_by_parity\n\n\ndef test_empty() -> None:\n    assert group_by_parity([]) == {'even': [], 'odd': []}\n\n\ndef test_negs() -> None:\n    assert group_by_parity([-3, -4, 0]) == {'even': [-4, 0], 'odd': [-3]}\n\n\ndef test_order() -> None:\n    assert group_by_parity([5, 2, 7]) == {'even': [2], 'odd': [5, 7]}\n",
        ),
        _p(
            "intersection_preserve_order",
            "ipo",
            "def intersection_preserve_order(xs: list[int], ys: list[int]) -> list[int]",
            "return values of xs that also appear in ys, in xs order, with duplicates removed.",
            "from ipo import intersection_preserve_order\n\n\ndef test_basic() -> None:\n    assert intersection_preserve_order([1, 2, 3, 4], [2, 4, 5]) == [2, 4]\n\n\ndef test_dedup() -> None:\n    assert intersection_preserve_order([1, 1, 2], [1, 2]) == [1, 2]\n",
            "from ipo import intersection_preserve_order\n\n\ndef test_none() -> None:\n    assert intersection_preserve_order([1, 2], [3, 4]) == []\n\n\ndef test_order() -> None:\n    assert intersection_preserve_order([5, 3, 1], [1, 3]) == [3, 1]\n\n\ndef test_empty() -> None:\n    assert intersection_preserve_order([], [1, 2]) == []\n",
        ),
        _p(
            "pairwise_sums",
            "pws",
            "def pairwise_sums(xs: list[int]) -> list[int]",
            "return the sums of each adjacent pair: out[i] = xs[i] + xs[i+1]; lists of length <2 yield [].",
            "from pws import pairwise_sums\n\n\ndef test_basic() -> None:\n    assert pairwise_sums([1, 2, 3, 4]) == [3, 5, 7]\n\n\ndef test_pair() -> None:\n    assert pairwise_sums([10, 20]) == [30]\n",
            "from pws import pairwise_sums\n\n\ndef test_single() -> None:\n    assert pairwise_sums([5]) == []\n\n\ndef test_empty() -> None:\n    assert pairwise_sums([]) == []\n\n\ndef test_negs() -> None:\n    assert pairwise_sums([-1, 1, -1]) == [0, 0]\n",
        ),
        _p(
            "cumulative_sum",
            "cs",
            "def cumulative_sum(xs: list[int]) -> list[int]",
            "return the running totals: out[i] = sum(xs[0..i]); empty input yields empty output.",
            "from cs import cumulative_sum\n\n\ndef test_basic() -> None:\n    assert cumulative_sum([1, 2, 3, 4]) == [1, 3, 6, 10]\n\n\ndef test_single() -> None:\n    assert cumulative_sum([5]) == [5]\n",
            "from cs import cumulative_sum\n\n\ndef test_empty() -> None:\n    assert cumulative_sum([]) == []\n\n\ndef test_negs() -> None:\n    assert cumulative_sum([3, -1, -1]) == [3, 2, 1]\n\n\ndef test_zeros() -> None:\n    assert cumulative_sum([0, 0, 5]) == [0, 0, 5]\n",
        ),
        _p(
            "second_largest",
            "sl",
            "def second_largest(xs: list[int]) -> int",
            "return the second largest distinct value in xs; xs has at least two distinct values.",
            "from sl import second_largest\n\n\ndef test_basic() -> None:\n    assert second_largest([3, 1, 4, 1, 5]) == 4\n\n\ndef test_dups() -> None:\n    assert second_largest([5, 5, 3]) == 3\n",
            "from sl import second_largest\n\n\ndef test_two() -> None:\n    assert second_largest([1, 2]) == 1\n\n\ndef test_negs() -> None:\n    assert second_largest([-1, -2, -3]) == -2\n\n\ndef test_mixed() -> None:\n    assert second_largest([10, 8, 10, 9]) == 9\n",
        ),
        # ── parsing / encoding ──
        _p(
            "binary_to_int",
            "b2i",
            "def binary_to_int(s: str) -> int",
            "the integer value of a binary string of '0'/'1' digits; binary_to_int('101') == 5, binary_to_int('0') == 0.",
            "from b2i import binary_to_int\n\n\ndef test_five() -> None:\n    assert binary_to_int('101') == 5\n\n\ndef test_zero() -> None:\n    assert binary_to_int('0') == 0\n",
            "from b2i import binary_to_int\n\n\ndef test_one() -> None:\n    assert binary_to_int('1') == 1\n\n\ndef test_fifteen() -> None:\n    assert binary_to_int('1111') == 15\n\n\ndef test_sixteen() -> None:\n    assert binary_to_int('10000') == 16\n",
        ),
        _p(
            "int_to_hex",
            "i2h",
            "def int_to_hex(n: int) -> str",
            "the lowercase hexadecimal representation of a non-negative int, no '0x' prefix; int_to_hex(0) == '0'.",
            "from i2h import int_to_hex\n\n\ndef test_ff() -> None:\n    assert int_to_hex(255) == 'ff'\n\n\ndef test_zero() -> None:\n    assert int_to_hex(0) == '0'\n",
            "from i2h import int_to_hex\n\n\ndef test_ten() -> None:\n    assert int_to_hex(16) == '10'\n\n\ndef test_fff() -> None:\n    assert int_to_hex(4095) == 'fff'\n\n\ndef test_one() -> None:\n    assert int_to_hex(1) == '1'\n",
        ),
        _p(
            "parse_key_values",
            "pkv",
            "def parse_key_values(s: str) -> dict[str, str]",
            "parse ';'-separated 'key=value' pairs into a dict; split each pair on its first '='; empty string -> {}.",
            "from pkv import parse_key_values\n\n\ndef test_two() -> None:\n    assert parse_key_values('a=1;b=2') == {'a': '1', 'b': '2'}\n\n\ndef test_one() -> None:\n    assert parse_key_values('name=bob') == {'name': 'bob'}\n",
            "from pkv import parse_key_values\n\n\ndef test_empty() -> None:\n    assert parse_key_values('') == {}\n\n\ndef test_value_eq() -> None:\n    assert parse_key_values('k=v=w') == {'k': 'v=w'}\n\n\ndef test_three() -> None:\n    assert parse_key_values('a=1;b=2;c=3') == {'a': '1', 'b': '2', 'c': '3'}\n",
        ),
        _p(
            "is_valid_ipv4",
            "ipv4",
            "def is_valid_ipv4(s: str) -> bool",
            "True iff s is a dotted IPv4 address: four decimal octets (digits only) each in 0..255 with no leading zeros.",
            "from ipv4 import is_valid_ipv4\n\n\ndef test_ok() -> None:\n    assert is_valid_ipv4('192.168.0.1') is True\n\n\ndef test_over() -> None:\n    assert is_valid_ipv4('256.1.1.1') is False\n",
            "from ipv4 import is_valid_ipv4\n\n\ndef test_zeros() -> None:\n    assert is_valid_ipv4('0.0.0.0') is True\n\n\ndef test_leading_zero() -> None:\n    assert is_valid_ipv4('01.1.1.1') is False\n\n\ndef test_three_parts() -> None:\n    assert is_valid_ipv4('1.2.3') is False\n\n\ndef test_max() -> None:\n    assert is_valid_ipv4('255.255.255.255') is True\n",
        ),
        _p(
            "parse_csv_line",
            "csvln",
            "def parse_csv_line(line: str) -> list[str]",
            "split one CSV line into fields on commas; a double-quoted field may contain commas; a doubled quote inside is a literal quote.",
            "from csvln import parse_csv_line\n\n\ndef test_plain() -> None:\n    assert parse_csv_line('a,b,c') == ['a', 'b', 'c']\n\n\ndef test_quoted_comma() -> None:\n    assert parse_csv_line('\"x,y\",z') == ['x,y', 'z']\n",
            "from csvln import parse_csv_line\n\n\ndef test_escaped_quote() -> None:\n    assert parse_csv_line('\"a\"\"b\",c') == ['a\"b', 'c']\n\n\ndef test_empty_fields() -> None:\n    assert parse_csv_line('a,,b') == ['a', '', 'b']\n\n\ndef test_single_quoted() -> None:\n    assert parse_csv_line('\"hi\"') == ['hi']\n\n\ndef test_inner() -> None:\n    assert parse_csv_line('1,\"2,3\",4') == ['1', '2,3', '4']\n",
        ),
        _p(
            "to_pig_latin",
            "pig",
            "def to_pig_latin(word: str) -> str",
            "pig-latin one lowercase word: vowel-start -> append 'way'; else move leading consonants to the end and append 'ay'.",
            "from pig import to_pig_latin\n\n\ndef test_pig() -> None:\n    assert to_pig_latin('pig') == 'igpay'\n\n\ndef test_apple() -> None:\n    assert to_pig_latin('apple') == 'appleway'\n",
            "from pig import to_pig_latin\n\n\ndef test_string() -> None:\n    assert to_pig_latin('string') == 'ingstray'\n\n\ndef test_trash() -> None:\n    assert to_pig_latin('trash') == 'ashtray'\n\n\ndef test_egg() -> None:\n    assert to_pig_latin('egg') == 'eggway'\n",
        ),
        _p(
            "count_words_per_line",
            "cwpl",
            "def count_words_per_line(s: str) -> list[int]",
            "split s into lines on newline and return the count of whitespace-separated words on each line; '' -> [0].",
            "from cwpl import count_words_per_line\n\n\ndef test_two_lines() -> None:\n    assert count_words_per_line('a b\\nc') == [2, 1]\n\n\ndef test_single() -> None:\n    assert count_words_per_line('one') == [1]\n",
            "from cwpl import count_words_per_line\n\n\ndef test_blank_line() -> None:\n    assert count_words_per_line('a b c\\n\\nd') == [3, 0, 1]\n\n\ndef test_empty() -> None:\n    assert count_words_per_line('') == [0]\n\n\ndef test_three() -> None:\n    assert count_words_per_line('x\\ny z\\nw') == [1, 2, 1]\n",
        ),
        _p(
            "parse_range",
            "prange",
            "def parse_range(s: str) -> list[int]",
            "expand a comma-separated range spec into a list of ints, in order; each token is an int or 'a-b' (inclusive).",
            "from prange import parse_range\n\n\ndef test_mixed() -> None:\n    assert parse_range('1-3,5') == [1, 2, 3, 5]\n\n\ndef test_single() -> None:\n    assert parse_range('5') == [5]\n",
            "from prange import parse_range\n\n\ndef test_two_ranges() -> None:\n    assert parse_range('1-3,7-8') == [1, 2, 3, 7, 8]\n\n\ndef test_singles() -> None:\n    assert parse_range('2,4,6') == [2, 4, 6]\n\n\ndef test_one_range() -> None:\n    assert parse_range('10-12') == [10, 11, 12]\n",
        ),
        _p(
            "rot13",
            "rot13",
            "def rot13(s: str) -> str",
            "apply ROT13 to ASCII letters (rotate 13, preserving case); leave other characters unchanged.",
            "from rot13 import rot13\n\n\ndef test_hello() -> None:\n    assert rot13('hello') == 'uryyb'\n\n\ndef test_abc() -> None:\n    assert rot13('abc') == 'nop'\n",
            "from rot13 import rot13\n\n\ndef test_roundtrip() -> None:\n    assert rot13(rot13('Substrate')) == 'Substrate'\n\n\ndef test_mixed() -> None:\n    assert rot13('Hello, World!') == 'Uryyb, Jbeyq!'\n\n\ndef test_upper() -> None:\n    assert rot13('ABC') == 'NOP'\n",
        ),
        _p(
            "normalize_whitespace",
            "nws",
            "def normalize_whitespace(s: str) -> str",
            "collapse every run of whitespace to a single space and strip leading/trailing whitespace.",
            "from nws import normalize_whitespace\n\n\ndef test_runs() -> None:\n    assert normalize_whitespace('  a   b ') == 'a b'\n\n\ndef test_clean() -> None:\n    assert normalize_whitespace('x y') == 'x y'\n",
            "from nws import normalize_whitespace\n\n\ndef test_tabs() -> None:\n    assert normalize_whitespace('a\\t\\tb\\nc') == 'a b c'\n\n\ndef test_empty() -> None:\n    assert normalize_whitespace('   ') == ''\n\n\ndef test_single() -> None:\n    assert normalize_whitespace('word') == 'word'\n",
        ),
        _p(
            "extract_numbers",
            "extnum",
            "def extract_numbers(s: str) -> list[int]",
            "return every maximal run of decimal digits in s, parsed as ints, in order; no digits -> [].",
            "from extnum import extract_numbers\n\n\ndef test_mixed() -> None:\n    assert extract_numbers('a1b22') == [1, 22]\n\n\ndef test_none() -> None:\n    assert extract_numbers('abc') == []\n",
            "from extnum import extract_numbers\n\n\ndef test_spaces() -> None:\n    assert extract_numbers('12 and 34') == [12, 34]\n\n\ndef test_empty() -> None:\n    assert extract_numbers('') == []\n\n\ndef test_leading() -> None:\n    assert extract_numbers('007x5') == [7, 5]\n",
        ),
        _p(
            "snake_to_camel",
            "s2c",
            "def snake_to_camel(s: str) -> str",
            "convert a lowercase snake_case identifier to camelCase: keep the first part, capitalize each later part.",
            "from s2c import snake_to_camel\n\n\ndef test_three() -> None:\n    assert snake_to_camel('foo_bar_baz') == 'fooBarBaz'\n\n\ndef test_single() -> None:\n    assert snake_to_camel('foo') == 'foo'\n",
            "from s2c import snake_to_camel\n\n\ndef test_two() -> None:\n    assert snake_to_camel('hello_world') == 'helloWorld'\n\n\ndef test_pair() -> None:\n    assert snake_to_camel('a_b') == 'aB'\n\n\ndef test_long() -> None:\n    assert snake_to_camel('my_var_name_here') == 'myVarNameHere'\n",
        ),
        # ── algorithms (second_largest dropped — already in lists) ──
        _p(
            "bubble_sort",
            "bsort",
            "def bubble_sort(xs: list[int]) -> list[int]",
            "a new list with the elements of xs sorted ascending (bubble sort); do not mutate the input.",
            "from bsort import bubble_sort\n\n\ndef test_basic() -> None:\n    assert bubble_sort([3, 1, 2]) == [1, 2, 3]\n\n\ndef test_dups() -> None:\n    assert bubble_sort([5, 5, 1, 5]) == [1, 5, 5, 5]\n",
            "from bsort import bubble_sort\n\n\ndef test_empty() -> None:\n    assert bubble_sort([]) == []\n\n\ndef test_sorted() -> None:\n    assert bubble_sort([1, 2, 3, 4]) == [1, 2, 3, 4]\n\n\ndef test_neg() -> None:\n    assert bubble_sort([0, -2, 4, -1]) == [-2, -1, 0, 4]\n",
        ),
        _p(
            "merge_two_sorted",
            "mts",
            "def merge_two_sorted(a: list[int], b: list[int]) -> list[int]",
            "merge two ascending-sorted lists into a single new ascending-sorted list containing all elements.",
            "from mts import merge_two_sorted\n\n\ndef test_interleave() -> None:\n    assert merge_two_sorted([1, 4, 7], [2, 3, 8]) == [1, 2, 3, 4, 7, 8]\n\n\ndef test_one_empty() -> None:\n    assert merge_two_sorted([], [2, 5]) == [2, 5]\n",
            "from mts import merge_two_sorted\n\n\ndef test_both_empty() -> None:\n    assert merge_two_sorted([], []) == []\n\n\ndef test_dups() -> None:\n    assert merge_two_sorted([1, 1, 2], [1, 3]) == [1, 1, 1, 2, 3]\n\n\ndef test_disjoint() -> None:\n    assert merge_two_sorted([5, 6], [1, 2]) == [1, 2, 5, 6]\n",
        ),
        _p(
            "max_subarray",
            "ms",
            "def max_subarray_sum(xs: list[int]) -> int",
            "the maximum sum of any non-empty contiguous subarray (Kadane); assume xs is non-empty.",
            "from ms import max_subarray_sum\n\n\ndef test_mixed() -> None:\n    assert max_subarray_sum([-2, 1, -3, 4, -1, 2, 1, -5, 4]) == 6\n\n\ndef test_allneg() -> None:\n    assert max_subarray_sum([-3, -1, -2]) == -1\n",
            "from ms import max_subarray_sum\n\n\ndef test_single() -> None:\n    assert max_subarray_sum([5]) == 5\n\n\ndef test_allpos() -> None:\n    assert max_subarray_sum([1, 2, 3]) == 6\n\n\ndef test_tail() -> None:\n    assert max_subarray_sum([-1, -2, 5, -1]) == 5\n",
        ),
        _p(
            "longest_increasing_run",
            "lir",
            "def longest_increasing_run(xs: list[int]) -> int",
            "the length of the longest strictly increasing contiguous run in xs; 0 for an empty list.",
            "from lir import longest_increasing_run\n\n\ndef test_mid() -> None:\n    assert longest_increasing_run([1, 2, 1, 2, 3, 4, 1]) == 4\n\n\ndef test_flat() -> None:\n    assert longest_increasing_run([3, 3, 3]) == 1\n",
            "from lir import longest_increasing_run\n\n\ndef test_empty() -> None:\n    assert longest_increasing_run([]) == 0\n\n\ndef test_all_up() -> None:\n    assert longest_increasing_run([1, 2, 3, 4, 5]) == 5\n\n\ndef test_strict() -> None:\n    assert longest_increasing_run([5, 1, 2, 2, 3]) == 2\n",
        ),
        _p(
            "is_sorted",
            "iss",
            "def is_sorted(xs: list[int]) -> bool",
            "True if xs is sorted non-decreasing (equal adjacent allowed); empty and single-element lists are sorted.",
            "from iss import is_sorted\n\n\ndef test_yes() -> None:\n    assert is_sorted([1, 2, 2, 3]) is True\n\n\ndef test_no() -> None:\n    assert is_sorted([1, 3, 2]) is False\n",
            "from iss import is_sorted\n\n\ndef test_empty() -> None:\n    assert is_sorted([]) is True\n\n\ndef test_single() -> None:\n    assert is_sorted([7]) is True\n\n\ndef test_desc() -> None:\n    assert is_sorted([3, 2, 1]) is False\n",
        ),
        _p(
            "find_missing_number",
            "fmn",
            "def find_missing_number(xs: list[int]) -> int",
            "xs holds n distinct ints, a subset of 0..n with exactly one missing; return the missing value (any order).",
            "from fmn import find_missing_number\n\n\ndef test_mid() -> None:\n    assert find_missing_number([0, 1, 3]) == 2\n\n\ndef test_first() -> None:\n    assert find_missing_number([1, 2, 3]) == 0\n",
            "from fmn import find_missing_number\n\n\ndef test_last() -> None:\n    assert find_missing_number([0, 1, 2]) == 3\n\n\ndef test_only() -> None:\n    assert find_missing_number([0]) == 1\n\n\ndef test_unordered() -> None:\n    assert find_missing_number([3, 0, 1, 4]) == 2\n",
        ),
        _p(
            "move_zeroes_to_end",
            "mze",
            "def move_zeroes_to_end(xs: list[int]) -> list[int]",
            "a new list with all zeroes moved to the end, preserving the relative order of the non-zero elements.",
            "from mze import move_zeroes_to_end\n\n\ndef test_basic() -> None:\n    assert move_zeroes_to_end([0, 1, 0, 3, 12]) == [1, 3, 12, 0, 0]\n\n\ndef test_order() -> None:\n    assert move_zeroes_to_end([4, 0, 5, 0, 6]) == [4, 5, 6, 0, 0]\n",
            "from mze import move_zeroes_to_end\n\n\ndef test_no_zero() -> None:\n    assert move_zeroes_to_end([1, 2, 3]) == [1, 2, 3]\n\n\ndef test_all_zero() -> None:\n    assert move_zeroes_to_end([0, 0, 0]) == [0, 0, 0]\n\n\ndef test_neg() -> None:\n    assert move_zeroes_to_end([0, -1, 0, -2]) == [-1, -2, 0, 0]\n",
        ),
        _p(
            "count_inversions",
            "ci",
            "def count_inversions(xs: list[int]) -> int",
            "the number of index pairs (i, j) with i < j and xs[i] > xs[j].",
            "from ci import count_inversions\n\n\ndef test_some() -> None:\n    assert count_inversions([2, 4, 1, 3, 5]) == 3\n\n\ndef test_sorted() -> None:\n    assert count_inversions([1, 2, 3]) == 0\n",
            "from ci import count_inversions\n\n\ndef test_reverse() -> None:\n    assert count_inversions([3, 2, 1]) == 3\n\n\ndef test_empty() -> None:\n    assert count_inversions([]) == 0\n\n\ndef test_dups() -> None:\n    assert count_inversions([1, 3, 2, 3, 1]) == 4\n",
        ),
        _p(
            "kth_largest",
            "kl",
            "def kth_largest(xs: list[int], k: int) -> int",
            "the k-th largest element by descending position (1-indexed, duplicates counted); assume 1 <= k <= len(xs).",
            "from kl import kth_largest\n\n\ndef test_first() -> None:\n    assert kth_largest([3, 1, 4, 1, 5], 1) == 5\n\n\ndef test_third() -> None:\n    assert kth_largest([3, 1, 4, 1, 5], 3) == 3\n",
            "from kl import kth_largest\n\n\ndef test_with_dups() -> None:\n    assert kth_largest([2, 2, 2], 2) == 2\n\n\ndef test_last() -> None:\n    assert kth_largest([10, 20, 30], 3) == 10\n\n\ndef test_neg() -> None:\n    assert kth_largest([-1, -5, -3], 2) == -3\n",
        ),
        _p(
            "dedup_sorted",
            "dsorted",
            "def dedup_sorted(xs: list[int]) -> list[int]",
            "given an ascending-sorted list, a new list with consecutive duplicates collapsed to one each, order preserved.",
            "from dsorted import dedup_sorted\n\n\ndef test_basic() -> None:\n    assert dedup_sorted([1, 1, 2, 3, 3, 3]) == [1, 2, 3]\n\n\ndef test_none() -> None:\n    assert dedup_sorted([1, 2, 3]) == [1, 2, 3]\n",
            "from dsorted import dedup_sorted\n\n\ndef test_empty() -> None:\n    assert dedup_sorted([]) == []\n\n\ndef test_all_same() -> None:\n    assert dedup_sorted([4, 4, 4, 4]) == [4]\n\n\ndef test_neg() -> None:\n    assert dedup_sorted([-2, -2, 0, 0, 1]) == [-2, 0, 1]\n",
        ),
        _p(
            "lcs_length",
            "lcs",
            "def longest_common_subsequence_length(a: str, b: str) -> int",
            "the length of the longest common subsequence of strings a and b (in order, not necessarily contiguous).",
            "from lcs import longest_common_subsequence_length\n\n\ndef test_basic() -> None:\n    assert longest_common_subsequence_length('abcde', 'ace') == 3\n\n\ndef test_none() -> None:\n    assert longest_common_subsequence_length('abc', 'def') == 0\n",
            "from lcs import longest_common_subsequence_length\n\n\ndef test_empty() -> None:\n    assert longest_common_subsequence_length('', 'abc') == 0\n\n\ndef test_same() -> None:\n    assert longest_common_subsequence_length('hello', 'hello') == 5\n\n\ndef test_partial() -> None:\n    assert longest_common_subsequence_length('AGGTAB', 'GXTXAYB') == 4\n",
        ),
    ]
