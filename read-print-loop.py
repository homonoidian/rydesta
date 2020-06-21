from rydesta import Reader, pretty

reader = Reader()
while True:
  line = input('>>> ')
  reader.update(line)
  print(pretty(reader, spaces=4))
