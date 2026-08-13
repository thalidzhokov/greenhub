//! Author: Albert Thalidzhokov (https://github.com/thalidzhokov)

fn fib(n: u32) -> u64 {
    let (mut a, mut b) = (0u64, 1u64);
    for _ in 0..n {
        let t = a + b;
        a = b;
        b = t;
    }
    a
}

fn gcd(mut a: u64, mut b: u64) -> u64 {
    while b != 0 {
        let t = a % b;
        a = b;
        b = t;
    }
    a
}

fn is_prime(n: u64) -> bool {
    if n < 2 {
        return false;
    }
    let mut i = 2;
    while i * i <= n {
        if n % i == 0 {
            return false;
        }
        i += 1;
    }
    true
}

fn binary_search(items: &[u64], target: u64) -> Option<usize> {
    let (mut lo, mut hi) = (0isize, items.len() as isize - 1);
    while lo <= hi {
        let mid = ((lo + hi) / 2) as usize;
        if items[mid] == target {
            return Some(mid);
        }
        if items[mid] < target {
            lo = mid as isize + 1;
        } else {
            hi = mid as isize - 1;
        }
    }
    None
}

fn main() {
    println!("fib(10) = {}", fib(10));
    println!("gcd(54, 24) = {}", gcd(54, 24));

    let primes: Vec<u64> = (2..50).filter(|&n| is_prime(n)).collect();
    println!("primes: {:?}", primes);

    let squares: Vec<u64> = (1..=19).map(|n| n * n).collect();
    println!("index of 144: {:?}", binary_search(&squares, 144));
}

// ===============================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================
