# SPDX-License-Identifier: PolyForm-Noncommercial-1.0.0
# Copyright (C) 2026 Peter Laffey
"""Bank verification — every firewalled problem is solvable AND the firewall is fair.

For each problem, a reference solution is run through BOTH the dev gate and the held-out gate (full
ruff + mypy --strict + pytest). If a reference fails either, the problem is malformed (or the dev and
held-out tests disagree) and this test catches it before any model run. One overfit case proves the
firewall has teeth (passes dev, fails held-out). Runs real subprocesses; no models.
"""

import pytest

from substrate.assay.coding import coding_oracle
from substrate.assay.coding_problems import coding_problem_bank
from substrate.topologies.coding_flow.gate import parse_artifacts, run_gate

# A correct solution per problem, as a drafter would emit it (`# path: <module>.py` + a fenced block).
_REFERENCES: dict[str, str] = {
    "rle": "# path: rle.py\n```python\n"
    "def run_length_encode(s: str) -> list[tuple[str, int]]:\n"
    "    out: list[tuple[str, int]] = []\n"
    "    for ch in s:\n"
    "        if out and out[-1][0] == ch:\n"
    "            out[-1] = (ch, out[-1][1] + 1)\n"
    "        else:\n"
    "            out.append((ch, 1))\n"
    "    return out\n```\n",
    "duration": "# path: duration.py\n```python\n"
    "import re\n\n\n"
    "def parse_duration(s: str) -> int:\n"
    "    total = 0\n"
    '    for value, unit in re.findall(r"(\\d+)([hms])", s):\n'
    '        total += int(value) * {"h": 3600, "m": 60, "s": 1}[unit]\n'
    "    return total\n```\n",
    "reverse_words": "# path: rw.py\n```python\n"
    "def reverse_words(s: str) -> str:\n"
    '    return " ".join(reversed(s.split()))\n```\n',
    "balanced": "# path: bal.py\n```python\n"
    "def is_balanced(s: str) -> bool:\n"
    '    pairs = {")": "(", "]": "[", "}": "{"}\n'
    "    stack: list[str] = []\n"
    "    for ch in s:\n"
    '        if ch in "([{":\n'
    "            stack.append(ch)\n"
    "        elif ch in pairs:\n"
    "            if not stack or stack.pop() != pairs[ch]:\n"
    "                return False\n"
    "    return not stack\n```\n",
    "two_sum": "# path: ts.py\n```python\n"
    "def two_sum(nums: list[int], target: int) -> tuple[int, int]:\n"
    "    seen: dict[int, int] = {}\n"
    "    for i, n in enumerate(nums):\n"
    "        if target - n in seen:\n"
    "            return (seen[target - n], i)\n"
    "        seen[n] = i\n"
    "    return (-1, -1)\n```\n",
    "roman": "# path: rom.py\n```python\n"
    "def roman_to_int(s: str) -> int:\n"
    '    vals = {"I": 1, "V": 5, "X": 10, "L": 50, "C": 100, "D": 500, "M": 1000}\n'
    "    total = 0\n"
    "    for i, ch in enumerate(s):\n"
    "        if i + 1 < len(s) and vals[ch] < vals[s[i + 1]]:\n"
    "            total -= vals[ch]\n"
    "        else:\n"
    "            total += vals[ch]\n"
    "    return total\n```\n",
    "fizzbuzz": "# path: fb.py\n```python\n"
    "def fizzbuzz(n: int) -> list[str]:\n"
    "    out: list[str] = []\n"
    "    for i in range(1, n + 1):\n"
    "        if i % 15 == 0:\n"
    '            out.append("FizzBuzz")\n'
    "        elif i % 3 == 0:\n"
    '            out.append("Fizz")\n'
    "        elif i % 5 == 0:\n"
    '            out.append("Buzz")\n'
    "        else:\n"
    "            out.append(str(i))\n"
    "    return out\n```\n",
    "caesar": "# path: caes.py\n```python\n"
    "def caesar(s: str, shift: int) -> str:\n"
    "    out: list[str] = []\n"
    "    for ch in s:\n"
    '        if "a" <= ch <= "z":\n'
    '            out.append(chr((ord(ch) - ord("a") + shift) % 26 + ord("a")))\n'
    "        else:\n"
    "            out.append(ch)\n"
    '    return "".join(out)\n```\n',
    "bsearch": "# path: bs.py\n```python\n"
    "def binary_search(xs: list[int], target: int) -> int:\n"
    "    lo, hi = 0, len(xs) - 1\n"
    "    while lo <= hi:\n"
    "        mid = (lo + hi) // 2\n"
    "        if xs[mid] == target:\n"
    "            return mid\n"
    "        if xs[mid] < target:\n"
    "            lo = mid + 1\n"
    "        else:\n"
    "            hi = mid - 1\n"
    "    return -1\n```\n",
    "word_count": "# path: wc.py\n```python\n"
    "def word_count(s: str) -> dict[str, int]:\n"
    "    counts: dict[str, int] = {}\n"
    "    for w in s.split():\n"
    "        counts[w] = counts.get(w, 0) + 1\n"
    "    return counts\n```\n",
    # ── numbers ──
    "gcd": "# path: gd.py\n```python\ndef gcd(a: int, b: int) -> int:\n    while b:\n        a, b = b, a % b\n    return a\n```\n",
    "lcm": "# path: lc.py\n```python\ndef lcm(a: int, b: int) -> int:\n    x, y = a, b\n    while y:\n        x, y = y, x % y\n    return a // x * b\n```\n",
    "is_prime": "# path: pr.py\n```python\ndef is_prime(n: int) -> bool:\n    if n < 2:\n        return False\n    i = 2\n    while i * i <= n:\n        if n % i == 0:\n            return False\n        i += 1\n    return True\n```\n",
    "factorial": "# path: fac.py\n```python\ndef factorial(n: int) -> int:\n    result = 1\n    for i in range(2, n + 1):\n        result *= i\n    return result\n```\n",
    "digit_sum": "# path: ds.py\n```python\ndef digit_sum(n: int) -> int:\n    total = 0\n    while n > 0:\n        total += n % 10\n        n //= 10\n    return total\n```\n",
    "sum_of_divisors": "# path: sd.py\n```python\ndef sum_of_divisors(n: int) -> int:\n    total = 0\n    for i in range(1, n + 1):\n        if n % i == 0:\n            total += i\n    return total\n```\n",
    "is_perfect": "# path: pf.py\n```python\ndef is_perfect(n: int) -> bool:\n    if n < 2:\n        return False\n    total = 1\n    i = 2\n    while i * i <= n:\n        if n % i == 0:\n            total += i\n            other = n // i\n            if other != i:\n                total += other\n        i += 1\n    return total == n\n```\n",
    "collatz_steps": "# path: col.py\n```python\ndef collatz_steps(n: int) -> int:\n    steps = 0\n    while n != 1:\n        n = n // 2 if n % 2 == 0 else 3 * n + 1\n        steps += 1\n    return steps\n```\n",
    "nth_fibonacci": "# path: fib.py\n```python\ndef nth_fibonacci(n: int) -> int:\n    a, b = 0, 1\n    for _ in range(n):\n        a, b = b, a + b\n    return a\n```\n",
    "count_set_bits": "# path: csb.py\n```python\ndef count_set_bits(n: int) -> int:\n    count = 0\n    while n > 0:\n        count += n & 1\n        n >>= 1\n    return count\n```\n",
    "reverse_integer": "# path: ri.py\n```python\ndef reverse_integer(n: int) -> int:\n    sign = -1 if n < 0 else 1\n    return sign * int(str(abs(n))[::-1])\n```\n",
    "is_armstrong": "# path: arm.py\n```python\ndef is_armstrong(n: int) -> bool:\n    digits = str(n)\n    power = len(digits)\n    total = 0\n    for d in digits:\n        total += int(d) ** power\n    return total == n\n```\n",
    "sum_even": "# path: se.py\n```python\ndef sum_even(n: int) -> int:\n    return sum(i for i in range(2, n + 1, 2))\n```\n",
    # ── strings ──
    "pal": "# path: pal.py\n```python\ndef is_palindrome(s: str) -> bool:\n    cleaned = [c.lower() for c in s if c.isalnum()]\n    return cleaned == cleaned[::-1]\n```\n",
    "anagram": "# path: anagram.py\n```python\ndef are_anagrams(a: str, b: str) -> bool:\n    def norm(x: str) -> list[str]:\n        return sorted(c.lower() for c in x if not c.isspace())\n    return norm(a) == norm(b)\n```\n",
    "vowels": "# path: vowels.py\n```python\ndef count_vowels(s: str) -> int:\n    return sum(1 for c in s if c.lower() in 'aeiou')\n```\n",
    "lcp": "# path: lcp.py\n```python\ndef longest_common_prefix(strs: list[str]) -> str:\n    if not strs:\n        return ''\n    prefix = strs[0]\n    for s in strs[1:]:\n        while not s.startswith(prefix):\n            prefix = prefix[:-1]\n            if not prefix:\n                return ''\n    return prefix\n```\n",
    "occur": "# path: occur.py\n```python\ndef count_occurrences(s: str, sub: str) -> int:\n    return s.count(sub)\n```\n",
    "dedup": "# path: dedup.py\n```python\ndef remove_duplicate_chars(s: str) -> str:\n    seen: set[str] = set()\n    out: list[str] = []\n    for c in s:\n        if c not in seen:\n            seen.add(c)\n            out.append(c)\n    return ''.join(out)\n```\n",
    "snake": "# path: snake.py\n```python\ndef to_snake_case(s: str) -> str:\n    out: list[str] = []\n    for i, c in enumerate(s):\n        if c.isupper():\n            if i > 0:\n                out.append('_')\n            out.append(c.lower())\n        else:\n            out.append(c)\n    return ''.join(out)\n```\n",
    "capwords": "# path: capwords.py\n```python\ndef capitalize_words(s: str) -> str:\n    return ' '.join(w[:1].upper() + w[1:].lower() for w in s.split())\n```\n",
    "freq": "# path: freq.py\n```python\ndef char_frequency_sorted(s: str) -> list[tuple[str, int]]:\n    counts: dict[str, int] = {}\n    for c in s:\n        counts[c] = counts.get(c, 0) + 1\n    return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))\n```\n",
    "firstuniq": "# path: firstuniq.py\n```python\ndef first_unique_char(s: str) -> int:\n    counts: dict[str, int] = {}\n    for c in s:\n        counts[c] = counts.get(c, 0) + 1\n    for i, c in enumerate(s):\n        if counts[c] == 1:\n            return i\n    return -1\n```\n",
    "strippunc": "# path: strippunc.py\n```python\nimport string\n\n\ndef strip_punctuation(s: str) -> str:\n    return ''.join(c for c in s if c not in string.punctuation)\n```\n",
    "mostchar": "# path: mostchar.py\n```python\ndef most_common_char(s: str) -> str:\n    counts: dict[str, int] = {}\n    for c in s:\n        counts[c] = counts.get(c, 0) + 1\n    best = ''\n    best_count = 0\n    for c in s:\n        if counts[c] > best_count:\n            best = c\n            best_count = counts[c]\n    return best\n```\n",
    # ── lists / dicts ──
    "flatten_one_level": "# path: fl.py\n```python\ndef flatten_one_level(xss: list[list[int]]) -> list[int]:\n    out: list[int] = []\n    for xs in xss:\n        out.extend(xs)\n    return out\n```\n",
    "dedup_preserve_order": "# path: dpo.py\n```python\ndef dedup_preserve_order(xs: list[int]) -> list[int]:\n    seen: set[int] = set()\n    out: list[int] = []\n    for x in xs:\n        if x not in seen:\n            seen.add(x)\n            out.append(x)\n    return out\n```\n",
    "rotate_left": "# path: rl.py\n```python\ndef rotate_left(xs: list[int], k: int) -> list[int]:\n    if not xs:\n        return []\n    k %= len(xs)\n    return xs[k:] + xs[:k]\n```\n",
    "running_max": "# path: rmax.py\n```python\ndef running_max(xs: list[int]) -> list[int]:\n    out: list[int] = []\n    cur = 0\n    for i, x in enumerate(xs):\n        cur = x if i == 0 else max(cur, x)\n        out.append(cur)\n    return out\n```\n",
    "most_common_element": "# path: mce.py\n```python\ndef most_common_element(xs: list[int]) -> int:\n    counts: dict[int, int] = {}\n    for x in xs:\n        counts[x] = counts.get(x, 0) + 1\n    best = xs[0]\n    for x in xs:\n        if counts[x] > counts[best]:\n            best = x\n    return best\n```\n",
    "transpose": "# path: tr.py\n```python\ndef transpose(matrix: list[list[int]]) -> list[list[int]]:\n    if not matrix:\n        return []\n    return [[row[i] for row in matrix] for i in range(len(matrix[0]))]\n```\n",
    "merge_dicts_summing_values": "# path: mds.py\n```python\ndef merge_dicts_summing_values(a: dict[str, int], b: dict[str, int]) -> dict[str, int]:\n    out: dict[str, int] = dict(a)\n    for k, v in b.items():\n        out[k] = out.get(k, 0) + v\n    return out\n```\n",
    "invert_dict": "# path: inv.py\n```python\ndef invert_dict(d: dict[str, int]) -> dict[int, str]:\n    return {v: k for k, v in d.items()}\n```\n",
    "group_by_parity": '# path: gbp.py\n```python\ndef group_by_parity(xs: list[int]) -> dict[str, list[int]]:\n    out: dict[str, list[int]] = {"even": [], "odd": []}\n    for x in xs:\n        out["even" if x % 2 == 0 else "odd"].append(x)\n    return out\n```\n',
    "intersection_preserve_order": "# path: ipo.py\n```python\ndef intersection_preserve_order(xs: list[int], ys: list[int]) -> list[int]:\n    yset = set(ys)\n    seen: set[int] = set()\n    out: list[int] = []\n    for x in xs:\n        if x in yset and x not in seen:\n            seen.add(x)\n            out.append(x)\n    return out\n```\n",
    "pairwise_sums": "# path: pws.py\n```python\ndef pairwise_sums(xs: list[int]) -> list[int]:\n    return [xs[i] + xs[i + 1] for i in range(len(xs) - 1)]\n```\n",
    "cumulative_sum": "# path: cs.py\n```python\ndef cumulative_sum(xs: list[int]) -> list[int]:\n    out: list[int] = []\n    total = 0\n    for x in xs:\n        total += x\n        out.append(total)\n    return out\n```\n",
    "second_largest": "# path: sl.py\n```python\ndef second_largest(xs: list[int]) -> int:\n    uniq = sorted(set(xs), reverse=True)\n    return uniq[1]\n```\n",
    # ── parsing / encoding ──
    "binary_to_int": "# path: b2i.py\n```python\ndef binary_to_int(s: str) -> int:\n    return int(s, 2)\n```\n",
    "int_to_hex": "# path: i2h.py\n```python\ndef int_to_hex(n: int) -> str:\n    return format(n, 'x')\n```\n",
    "parse_key_values": "# path: pkv.py\n```python\ndef parse_key_values(s: str) -> dict[str, str]:\n    out: dict[str, str] = {}\n    if not s:\n        return out\n    for pair in s.split(';'):\n        key, _, value = pair.partition('=')\n        out[key] = value\n    return out\n```\n",
    "is_valid_ipv4": "# path: ipv4.py\n```python\ndef is_valid_ipv4(s: str) -> bool:\n    parts = s.split('.')\n    if len(parts) != 4:\n        return False\n    for part in parts:\n        if not part.isdigit():\n            return False\n        if len(part) > 1 and part[0] == '0':\n            return False\n        if int(part) > 255:\n            return False\n    return True\n```\n",
    "parse_csv_line": "# path: csvln.py\n```python\ndef parse_csv_line(line: str) -> list[str]:\n    fields: list[str] = []\n    field: list[str] = []\n    i = 0\n    n = len(line)\n    in_quotes = False\n    while i < n:\n        ch = line[i]\n        if in_quotes:\n            if ch == '\"':\n                if i + 1 < n and line[i + 1] == '\"':\n                    field.append('\"')\n                    i += 2\n                    continue\n                in_quotes = False\n                i += 1\n                continue\n            field.append(ch)\n            i += 1\n            continue\n        if ch == '\"':\n            in_quotes = True\n            i += 1\n            continue\n        if ch == ',':\n            fields.append(''.join(field))\n            field = []\n            i += 1\n            continue\n        field.append(ch)\n        i += 1\n    fields.append(''.join(field))\n    return fields\n```\n",
    "to_pig_latin": "# path: pig.py\n```python\ndef to_pig_latin(word: str) -> str:\n    vowels = 'aeiou'\n    if word and word[0] in vowels:\n        return word + 'way'\n    i = 0\n    while i < len(word) and word[i] not in vowels:\n        i += 1\n    return word[i:] + word[:i] + 'ay'\n```\n",
    "count_words_per_line": "# path: cwpl.py\n```python\ndef count_words_per_line(s: str) -> list[int]:\n    return [len(line.split()) for line in s.split('\\n')]\n```\n",
    "parse_range": "# path: prange.py\n```python\ndef parse_range(s: str) -> list[int]:\n    out: list[int] = []\n    for token in s.split(','):\n        if '-' in token:\n            lo_s, _, hi_s = token.partition('-')\n            out.extend(range(int(lo_s), int(hi_s) + 1))\n        else:\n            out.append(int(token))\n    return out\n```\n",
    "rot13": "# path: rot13.py\n```python\n_TABLE = str.maketrans(\n    'abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ',\n    'nopqrstuvwxyzabcdefghijklmNOPQRSTUVWXYZABCDEFGHIJKLM',\n)\n\n\ndef rot13(s: str) -> str:\n    return s.translate(_TABLE)\n```\n",
    "normalize_whitespace": "# path: nws.py\n```python\ndef normalize_whitespace(s: str) -> str:\n    return ' '.join(s.split())\n```\n",
    "extract_numbers": "# path: extnum.py\n```python\nimport re\n\n\ndef extract_numbers(s: str) -> list[int]:\n    return [int(m) for m in re.findall(r'\\d+', s)]\n```\n",
    "snake_to_camel": "# path: s2c.py\n```python\ndef snake_to_camel(s: str) -> str:\n    parts = s.split('_')\n    return parts[0] + ''.join(p.capitalize() for p in parts[1:])\n```\n",
    # ── algorithms ──
    "bubble_sort": "# path: bsort.py\n```python\ndef bubble_sort(xs: list[int]) -> list[int]:\n    ys = list(xs)\n    n = len(ys)\n    for i in range(n):\n        for j in range(n - 1 - i):\n            if ys[j] > ys[j + 1]:\n                ys[j], ys[j + 1] = ys[j + 1], ys[j]\n    return ys\n```\n",
    "merge_two_sorted": "# path: mts.py\n```python\ndef merge_two_sorted(a: list[int], b: list[int]) -> list[int]:\n    out: list[int] = []\n    i = j = 0\n    while i < len(a) and j < len(b):\n        if a[i] <= b[j]:\n            out.append(a[i])\n            i += 1\n        else:\n            out.append(b[j])\n            j += 1\n    out.extend(a[i:])\n    out.extend(b[j:])\n    return out\n```\n",
    "max_subarray": "# path: ms.py\n```python\ndef max_subarray_sum(xs: list[int]) -> int:\n    best = cur = xs[0]\n    for x in xs[1:]:\n        cur = max(x, cur + x)\n        best = max(best, cur)\n    return best\n```\n",
    "longest_increasing_run": "# path: lir.py\n```python\ndef longest_increasing_run(xs: list[int]) -> int:\n    if not xs:\n        return 0\n    best = cur = 1\n    for i in range(1, len(xs)):\n        if xs[i] > xs[i - 1]:\n            cur += 1\n        else:\n            cur = 1\n        best = max(best, cur)\n    return best\n```\n",
    "is_sorted": "# path: iss.py\n```python\ndef is_sorted(xs: list[int]) -> bool:\n    return all(xs[i] <= xs[i + 1] for i in range(len(xs) - 1))\n```\n",
    "find_missing_number": "# path: fmn.py\n```python\ndef find_missing_number(xs: list[int]) -> int:\n    n = len(xs)\n    return n * (n + 1) // 2 - sum(xs)\n```\n",
    "move_zeroes_to_end": "# path: mze.py\n```python\ndef move_zeroes_to_end(xs: list[int]) -> list[int]:\n    nonzero = [x for x in xs if x != 0]\n    zeros = [0] * (len(xs) - len(nonzero))\n    return nonzero + zeros\n```\n",
    "count_inversions": "# path: ci.py\n```python\ndef count_inversions(xs: list[int]) -> int:\n    count = 0\n    n = len(xs)\n    for i in range(n):\n        for j in range(i + 1, n):\n            if xs[i] > xs[j]:\n                count += 1\n    return count\n```\n",
    "kth_largest": "# path: kl.py\n```python\ndef kth_largest(xs: list[int], k: int) -> int:\n    return sorted(xs, reverse=True)[k - 1]\n```\n",
    "dedup_sorted": "# path: dsorted.py\n```python\ndef dedup_sorted(xs: list[int]) -> list[int]:\n    out: list[int] = []\n    for x in xs:\n        if not out or out[-1] != x:\n            out.append(x)\n    return out\n```\n",
    "lcs_length": "# path: lcs.py\n```python\ndef longest_common_subsequence_length(a: str, b: str) -> int:\n    m, n = len(a), len(b)\n    dp = [[0] * (n + 1) for _ in range(m + 1)]\n    for i in range(1, m + 1):\n        for j in range(1, n + 1):\n            if a[i - 1] == b[j - 1]:\n                dp[i][j] = dp[i - 1][j - 1] + 1\n            else:\n                dp[i][j] = max(dp[i - 1][j], dp[i][j - 1])\n    return dp[m][n]\n```\n",
}


def test_bank_is_nontrivial_and_each_problem_has_a_reference() -> None:
    bank = coding_problem_bank()
    assert len(bank) >= 10
    ids = [p.problem_id for p in bank]
    assert len(set(ids)) == len(ids)  # unique
    assert set(ids) == set(_REFERENCES)  # every problem has a reference


@pytest.mark.parametrize("problem", coding_problem_bank(), ids=lambda p: p.problem_id)
def test_reference_passes_both_gates(problem) -> None:
    # the reference must pass the DEV gate (solvable) AND the HELD-OUT gate (the held-out tests agree
    # with the dev tests on a correct solution — the firewall is fair, not impossible).
    ref = _REFERENCES[problem.problem_id]
    arts = parse_artifacts(ref)
    dev = run_gate({**arts, **problem.dev_fixtures}, problem.dev_gate)
    assert dev.passed, f"{problem.problem_id} reference failed DEV gate:\n{dev.summary}"
    grade = run_gate({**arts, **problem.grading_tests}, problem.grading_command)
    assert grade.passed, f"{problem.problem_id} reference failed HELD-OUT gate:\n{grade.summary}"


def test_firewall_has_teeth_on_a_real_problem() -> None:
    # an overfit fizzbuzz that special-cases only the dev inputs (n in {3, 5}) passes dev but fails the
    # held-out gate via the oracle — the firewall catches teaching-to-the-test.
    problem = next(p for p in coding_problem_bank() if p.problem_id == "fizzbuzz")
    overfit = (
        "# path: fb.py\n```python\n"
        "def fizzbuzz(n: int) -> list[str]:\n"
        "    if n == 3:\n"
        "        return ['1', '2', 'Fizz']\n"
        "    return ['1', '2', 'Fizz', '4', 'Buzz']\n```\n"
    )
    record = [
        {"kind": "Candidate", "payload": {"round": 1, "slot": 0, "response": overfit}},
        {"kind": "Solved", "payload": {"round": 1, "slot": 0}},
    ]
    # it passes the dev gate...
    dev = run_gate({**parse_artifacts(overfit), **problem.dev_fixtures}, problem.dev_gate)
    assert dev.passed
    # ...but the oracle (held-out) catches it.
    assert coding_oracle().grade(record, problem).passed is False
