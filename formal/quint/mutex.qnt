module mutex {
  var locked: bool
  var holders: int
  action Init = all {
    locked' = false,
    holders' = 0
  }
  action Acquire = all {
    locked == false,
    locked' = true,
    holders' = 1
  }
  action Release = all {
    locked == true,
    locked' = false,
    holders' = 0
  }
  action Next = any { Acquire, Release }
  val MutualExclusion = holders <= 1
}
