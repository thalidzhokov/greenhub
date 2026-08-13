/**
 * @file example.ts
 * @author Albert Thalidzhokov <https://github.com/thalidzhokov>
 */

function fib(n: number): number {
  let [a, b] = [0, 1];
  for (let i = 0; i < n; i++) {
    [a, b] = [b, a + b];
  }
  return a;
}

function gcd(a: number, b: number): number {
  while (b !== 0) {
    [a, b] = [b, a % b];
  }
  return a;
}

function isPrime(n: number): boolean {
  if (n < 2) {
    return false;
  }
  for (let i = 2; i * i <= n; i++) {
    if (n % i === 0) {
      return false;
    }
  }
  return true;
}

function binarySearch(items: readonly number[], target: number): number {
  let lo = 0;
  let hi = items.length - 1;
  while (lo <= hi) {
    const mid = Math.floor((lo + hi) / 2);
    if (items[mid] === target) {
      return mid;
    }
    if (items[mid] < target) {
      lo = mid + 1;
    } else {
      hi = mid - 1;
    }
  }
  return -1;
}

const primes: number[] = [];
for (let n = 2; n < 50; n++) {
  if (isPrime(n)) {
    primes.push(n);
  }
}

const squares = Array.from({ length: 19 }, (_, i) => (i + 1) * (i + 1));

console.log("fib(10) =", fib(10));
console.log("gcd(54, 24) =", gcd(54, 24));
console.log("primes:", primes.join(" "));
console.log("index of 144:", binarySearch(squares, 144));

// ================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================
