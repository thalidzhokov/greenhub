/*
 * Author: Albert Thalidzhokov (https://github.com/thalidzhokov)
 */

fun fib(n: Int): Long {
    var a = 0L
    var b = 1L
    repeat(n) {
        val t = a + b
        a = b
        b = t
    }
    return a
}

fun gcd(x: Int, y: Int): Int {
    var a = x
    var b = y
    while (b != 0) {
        val t = a % b
        a = b
        b = t
    }
    return a
}

fun isPrime(n: Int): Boolean {
    if (n < 2) return false
    var i = 2
    while (i * i <= n) {
        if (n % i == 0) return false
        i++
    }
    return true
}

fun binarySearch(items: List<Int>, target: Int): Int {
    var lo = 0
    var hi = items.size - 1
    while (lo <= hi) {
        val mid = (lo + hi) / 2
        when {
            items[mid] == target -> return mid
            items[mid] < target -> lo = mid + 1
            else -> hi = mid - 1
        }
    }
    return -1
}

fun main() {
    println("fib(10) = ${fib(10)}")
    println("gcd(54, 24) = ${gcd(54, 24)}")

    val primes = (2 until 50).filter(::isPrime)
    println("primes: $primes")

    val squares = (1..19).map { it * it }
    println("index of 144: ${binarySearch(squares, 144)}")
}

// ==================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================
