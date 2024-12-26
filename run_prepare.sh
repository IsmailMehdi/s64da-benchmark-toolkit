./prepare_benchmark \
    --dsn postgresql://postgres@localhost/tpcds_v \
    --benchmark tpcds \
    --schema=psql_native \
    --scale-factor=10