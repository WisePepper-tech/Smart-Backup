package main

deny[msg] {
  input[i].Cmd == "run"
  contains(lower(input[i].Value[0]), "curl")
  msg = "Curl is not allowed in Dockerfile"
}

deny[msg] {
  input[i].Cmd == "run"
  contains(lower(input[i].Value[0]), "wget")
  msg = "Wget is not allowed in Dockerfile"
}