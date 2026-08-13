/**
 * @author Albert Thalidzhokov (https://github.com/thalidzhokov)
 */
object Main {
  def fib(n: Int): Long = {
    var (a, b) = (0L, 1L)
    for (_ <- 0 until n) {
      val t = a + b
      a = b
      b = t
    }
    a
  }

  def gcd(a: Int, b: Int): Int =
    if (b == 0) a else gcd(b, a % b)

  def isPrime(n: Int): Boolean =
    n >= 2 && (2 to math.sqrt(n.toDouble).toInt).forall(n % _ != 0)

  def binarySearch(items: Vector[Int], target: Int): Int = {
    @annotation.tailrec
    def loop(lo: Int, hi: Int): Int =
      if (lo > hi) -1
      else {
        val mid = (lo + hi) / 2
        if (items(mid) == target) mid
        else if (items(mid) < target) loop(mid + 1, hi)
        else loop(lo, mid - 1)
      }

    loop(0, items.length - 1)
  }

  def main(args: Array[String]): Unit = {
    println(s"fib(10) = ${fib(10)}")
    println(s"gcd(54, 24) = ${gcd(54, 24)}")

    val primes = (2 until 50).filter(isPrime)
    println(s"primes: ${primes.mkString(" ")}")

    val squares = (1 to 19).map(n => n * n).toVector
    println(s"index of 144: ${binarySearch(squares, 144)}")
  }
}

// ===============================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================================
