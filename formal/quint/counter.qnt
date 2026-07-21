module counter {
  var x: int
  action Init = { x' = 0 }
  action Inc = { x' = x + 1 }
  action Next = Inc
  val NonNeg = x >= 0
}
