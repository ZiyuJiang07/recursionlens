window.RL_EXAMPLES = [
  {
    "lecture": "Lecture 4 · Iteration",
    "name": "loop_to",
    "call": "loop_to(1)",
    "note": "adapted: the lecture reads num from input()",
    "code": "num = 5\n\ndef loop_to(n):\n    print(n)\n    if n < num:\n        loop_to(n + 1)\n"
  },
  {
    "lecture": "Lecture 6 · Functional Programming",
    "name": "gcd",
    "call": "gcd(48, 18)",
    "note": "",
    "code": "def gcd(a, b):\n    return gcd(b, a % b) if b else abs(a)\n"
  },
  {
    "lecture": "Lecture 6 · Functional Programming",
    "name": "fibonacci",
    "call": "fibonacci(6)",
    "note": "",
    "code": "def fibonacci(n):\n    if n > 1:\n        return fibonacci(n - 1) + fibonacci(n - 2)  # recursion\n    elif n == 1:\n        return 1\n    else:\n        return 0\n"
  },
  {
    "lecture": "Lecture 6 · Generator and Decorator",
    "name": "fibonacci (printing)",
    "call": "fibonacci(4)",
    "note": "prints the call tree while it runs",
    "code": "count, depth = 0, -1\n\ndef fibonacci(n):\n    \"\"\"Returns the Fibonacci number of order n.\"\"\"\n    global count, depth\n    count += 1\n    depth += 1\n    print(\"{:>3}: {}fibonacci({!r})\".format(count, \"|\" * depth, n))\n\n    value = fibonacci(n - 1) + fibonacci(n - 2) if n > 1 else 1 if n == 1 else 0\n\n    depth -= 1\n    if depth == -1:  # recursion done\n        print(\"Done\")\n        count = 0  # reset count for subsequent recursions\n    return value\n"
  },
  {
    "lecture": "Lecture 8 · Sequence Types",
    "name": "quicksort",
    "call": "quicksort([3, 1, 2, 5, 4])",
    "note": "",
    "code": "import random\n\ndef quicksort(seq):\n    \"\"\"Return a sorted list of items from seq.\"\"\"\n    if len(seq) <= 1:\n        return list(seq)\n    i = random.randint(0, len(seq) - 1)\n    pivot, others = seq[i], [*seq[:i], *seq[i + 1:]]\n    left = quicksort([x for x in others if x < pivot])\n    right = quicksort([x for x in others if x >= pivot])\n    return [*left, pivot, *right]\n"
  }
];
