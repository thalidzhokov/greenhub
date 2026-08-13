/**
 * @file example.c
 * @author Albert Thalidzhokov (https://github.com/thalidzhokov)
 */

#include <stdbool.h>
#include <stdio.h>

int fib(int n) {
    int a = 0, b = 1;
    while (n-- > 0) {
        int t = a + b;
        a = b;
        b = t;
    }
    return a;
}

int gcd(int a, int b) {
    while (b != 0) {
        int t = a % b;
        a = b;
        b = t;
    }
    return a;
}

bool is_prime(int n) {
    if (n < 2) {
        return false;
    }
    for (int i = 2; i * i <= n; i++) {
        if (n % i == 0) {
            return false;
        }
    }
    return true;
}

int binary_search(const int *items, int size, int target) {
    int lo = 0, hi = size - 1;
    while (lo <= hi) {
        int mid = lo + (hi - lo) / 2;
        if (items[mid] == target) {
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

int main(void) {
    printf("fib(10) = %d\n", fib(10));
    printf("gcd(54, 24) = %d\n", gcd(54, 24));

    printf("primes:");
    for (int n = 2; n < 50; n++) {
        if (is_prime(n)) {
            printf(" %d", n);
        }
    }
    printf("\n");

    int squares[19];
    for (int i = 0; i < 19; i++) {
        squares[i] = (i + 1) * (i + 1);
    }
    printf("index of 144 = %d\n", binary_search(squares, 19, 144));
    return 0;
}

// ================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================
