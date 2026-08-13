#!/usr/bin/env bash
# Author: Albert Thalidzhokov (https://github.com/thalidzhokov)

set -euo pipefail

fib() {
    local n=$1 a=0 b=1 t
    while (( n-- > 0 )); do
        t=$(( a + b ))
        a=$b
        b=$t
    done
    echo "$a"
}

gcd() {
    local a=$1 b=$2 t
    while (( b != 0 )); do
        t=$(( a % b ))
        a=$b
        b=$t
    done
    echo "$a"
}

is_prime() {
    local n=$1 i
    (( n < 2 )) && return 1
    for (( i = 2; i * i <= n; i++ )); do
        (( n % i == 0 )) && return 1
    done
    return 0
}

binary_search() {
    local target=$1
    shift
    local items=("$@")
    local lo=0 hi=$(( $# - 1 )) mid
    while (( lo <= hi )); do
        mid=$(( (lo + hi) / 2 ))
        if (( items[mid] == target )); then
            echo "$mid"
            return
        fi
        if (( items[mid] < target )); then
            lo=$(( mid + 1 ))
        else
            hi=$(( mid - 1 ))
        fi
    done
    echo -1
}

main() {
    echo "fib(10) = $(fib 10)"
    echo "gcd(54, 24) = $(gcd 54 24)"

    local primes=() n
    for (( n = 2; n < 50; n++ )); do
        is_prime "$n" && primes+=("$n")
    done
    echo "primes: ${primes[*]}"

    local squares=() i
    for (( i = 1; i <= 19; i++ )); do
        squares+=( $(( i * i )) )
    done
    echo "index of 144 = $(binary_search 144 "${squares[@]}")"
}

main "$@"

# =====================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================
