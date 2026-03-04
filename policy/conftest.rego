package main

import rego.v1

deny[msg] {
  input[i].Cmd == "from"
  not contains(input[i].Value[0], "@sha256:")
  msg = "Base image must be pinned by digest"
}