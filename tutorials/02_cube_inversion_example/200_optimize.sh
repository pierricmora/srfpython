mkdir optimize
cd optimize || exit 1

# =============== using all nodes
HerrMet --optimize -init ../nodes.txt \
  -data 1. 0.0 \
  -prior  100. 1.0 \
          200. 2.0 \
          1 \
          1.0 0.5 \
  -upd 3 0 \
  -save
