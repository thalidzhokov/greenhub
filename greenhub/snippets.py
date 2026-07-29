"""Сниппеты кода для генерируемых коммитов: язык -> (файл, префикс комментария, код)."""

LANGUAGES: dict[str, tuple[str, str, str]] = {
    "c": (
        "main.c",
        "//",
        """#include <stdio.h>

int fib(int n) {
    int a = 0, b = 1;
    while (n-- > 0) {
        int t = a + b;
        a = b;
        b = t;
    }
    return a;
}

int main(void) {
    printf("%d\\n", fib(10));
    return 0;
}
""",
    ),
    "c++": (
        "main.cpp",
        "//",
        """#include <iostream>
#include <vector>

int main() {
    std::vector<int> fib{0, 1};
    while (fib.size() < 10) {
        fib.push_back(fib[fib.size() - 1] + fib[fib.size() - 2]);
    }
    for (int n : fib) {
        std::cout << n << ' ';
    }
    std::cout << '\\n';
    return 0;
}
""",
    ),
    "c#": (
        "Program.cs",
        "//",
        """var fib = new List<long> { 0, 1 };
while (fib.Count < 10)
{
    fib.Add(fib[^1] + fib[^2]);
}
Console.WriteLine(string.Join(" ", fib));
""",
    ),
    "go": (
        "main.go",
        "//",
        """package main

import "fmt"

func fib(n int) int {
    a, b := 0, 1
    for i := 0; i < n; i++ {
        a, b = b, a+b
    }
    return a
}

func main() {
    fmt.Println(fib(10))
}
""",
    ),
    "java": (
        "Main.java",
        "//",
        """public class Main {
    static int fib(int n) {
        int a = 0, b = 1;
        for (int i = 0; i < n; i++) {
            int t = a + b;
            a = b;
            b = t;
        }
        return a;
    }

    public static void main(String[] args) {
        System.out.println(fib(10));
    }
}
""",
    ),
    "javascript": (
        "index.js",
        "//",
        """function fib(n) {
  let [a, b] = [0, 1];
  for (let i = 0; i < n; i++) {
    [a, b] = [b, a + b];
  }
  return a;
}

console.log(fib(10));
""",
    ),
    "kotlin": (
        "Main.kt",
        "//",
        """fun fib(n: Int): Int {
    var (a, b) = 0 to 1
    repeat(n) {
        val t = a + b
        a = b
        b = t
    }
    return a
}

fun main() {
    println(fib(10))
}
""",
    ),
    "php": (
        "index.php",
        "//",
        """<?php

function fib(int $n): int
{
    [$a, $b] = [0, 1];
    for ($i = 0; $i < $n; $i++) {
        [$a, $b] = [$b, $a + $b];
    }
    return $a;
}

echo fib(10), PHP_EOL;
""",
    ),
    "python": (
        "main.py",
        "#",
        """def fib(n: int) -> int:
    a, b = 0, 1
    for _ in range(n):
        a, b = b, a + b
    return a


if __name__ == "__main__":
    print(fib(10))
""",
    ),
    "ruby": (
        "main.rb",
        "#",
        """def fib(n)
  a, b = 0, 1
  n.times { a, b = b, a + b }
  a
end

puts fib(10)
""",
    ),
    "rust": (
        "main.rs",
        "//",
        """fn fib(n: u32) -> u64 {
    let (mut a, mut b) = (0u64, 1u64);
    for _ in 0..n {
        let t = a + b;
        a = b;
        b = t;
    }
    a
}

fn main() {
    println!("{}", fib(10));
}
""",
    ),
    "scala": (
        "Main.scala",
        "//",
        """object Main {
  def fib(n: Int): Int =
    (1 to n).foldLeft((0, 1)) { case ((a, b), _) => (b, a + b) }._1

  def main(args: Array[String]): Unit =
    println(fib(10))
}
""",
    ),
    "swift": (
        "main.swift",
        "//",
        """func fib(_ n: Int) -> Int {
    var (a, b) = (0, 1)
    for _ in 0..<n {
        (a, b) = (b, a + b)
    }
    return a
}

print(fib(10))
""",
    ),
    "typescript": (
        "index.ts",
        "//",
        """function fib(n: number): number {
  let [a, b] = [0, 1];
  for (let i = 0; i < n; i++) {
    [a, b] = [b, a + b];
  }
  return a;
}

console.log(fib(10));
""",
    ),
}
