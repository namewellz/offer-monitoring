#!/usr/bin/env bash
export LANG=C.UTF-8
set -u

declare -a depts=(
  "Higiene"
  "Bazar e Utilidades"
  "Limpeza"
  "Doces e Sobremesas"
  "Padaria"
  "Hortifruti"
  "Congelados"
  "Pet Shop"
  "Saudáveis e Orgânicos"
  "Peixaria"
)

for d in "${depts[@]}"; do
  echo "================ RUN: $d ================"
  python -m scripts.classify_department --department "$d" --persist
  code=$?
  echo "================ DONE: $d (exit $code) ================"
done

echo "================ RUN: Outros (descoberta) ================"
python -m scripts.classify_outros --persist
code=$?
echo "================ DONE: Outros (exit $code) ================"

echo "ALL_REMAINING_DEPTS_DONE"
