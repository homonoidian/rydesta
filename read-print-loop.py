import readline

from rydesta import Master

master = Master('<interactive>')
master.kernel()
master.load_init()

while True:
  line = input('>>> ')
  print(master.feed(line))
