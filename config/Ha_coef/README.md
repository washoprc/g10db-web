# Ha_coef

旧 PHP `TekeTekeKun/Ha_coef/` の校正係数を配置する。

## 取り込み

```bash
./scripts/syncFromLegacy.sh /path/to/g10db
# または
cp -a /path/to/g10db/TekeTekeKun/Ha_coef/. config/Ha_coef/
```

`washoprc/g10db` への GitHub App アクセスが付与されたら上記を実行し、
テンプレート `ha_coef.txt` / `coef_example.txt` を実ファイルで置き換える。
