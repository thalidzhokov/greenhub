import java.util.ArrayList;
import java.util.List;

/**
 * @author Albert Thalidzhokov (https://github.com/thalidzhokov)
 */
public class Main {
    static long fib(int n) {
        long a = 0, b = 1;
        for (int i = 0; i < n; i++) {
            long t = a + b;
            a = b;
            b = t;
        }
        return a;
    }

    static int gcd(int a, int b) {
        while (b != 0) {
            int t = a % b;
            a = b;
            b = t;
        }
        return a;
    }

    static boolean isPrime(int n) {
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

    static int binarySearch(int[] items, int target) {
        int lo = 0, hi = items.length - 1;
        while (lo <= hi) {
            int mid = (lo + hi) / 2;
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

    public static void main(String[] args) {
        System.out.println("fib(10) = " + fib(10));
        System.out.println("gcd(54, 24) = " + gcd(54, 24));

        List<Integer> primes = new ArrayList<>();
        for (int n = 2; n < 50; n++) {
            if (isPrime(n)) {
                primes.add(n);
            }
        }
        System.out.println("primes: " + primes);

        int[] squares = new int[19];
        for (int i = 0; i < squares.length; i++) {
            squares[i] = (i + 1) * (i + 1);
        }
        System.out.println("index of 144: " + binarySearch(squares, 144));
    }
}

// ==================================================================================================================================================================================================================================================================================
