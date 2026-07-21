module smoke {
  var n: int
  action Init = { n' = 1 }
  action Next = { n' = n }
  val Positive = n > 0
}
