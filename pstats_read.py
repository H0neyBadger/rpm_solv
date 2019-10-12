import pstats
p = pstats.Stats('solv/cProfile')
p.sort_stats('cumulative').print_stats(30)
