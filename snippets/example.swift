//
//  example.swift
//
//  Created by Albert Thalidzhokov
//  https://github.com/thalidzhokov
//

func fib(_ n: Int) -> Int {
    var (a, b) = (0, 1)
    for _ in 0..<n {
        (a, b) = (b, a + b)
    }
    return a
}

func gcd(_ x: Int, _ y: Int) -> Int {
    var (a, b) = (x, y)
    while b != 0 {
        (a, b) = (b, a % b)
    }
    return a
}

func isPrime(_ n: Int) -> Bool {
    if n < 2 {
        return false
    }
    var i = 2
    while i * i <= n {
        if n % i == 0 {
            return false
        }
        i += 1
    }
    return true
}

func binarySearch(_ items: [Int], _ target: Int) -> Int {
    var lo = 0
    var hi = items.count - 1
    while lo <= hi {
        let mid = (lo + hi) / 2
        if items[mid] == target {
            return mid
        }
        if items[mid] < target {
            lo = mid + 1
        } else {
            hi = mid - 1
        }
    }
    return -1
}

let primes = (2..<50).filter(isPrime)
let squares = (1...19).map { $0 * $0 }

print("fib(10) =", fib(10))
print("gcd(54, 24) =", gcd(54, 24))
print("primes:", primes.map(String.init).joined(separator: " "))
print("index of 144:", binarySearch(squares, 144))

// ==================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================
