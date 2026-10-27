# References and licensing

The project implementation and documentation are released under the MIT license in `LICENSE`. The repository does not distribute the game, game assets, captured user profiles or third-party server implementations.

- [ndoa/Kelbi TPDU protocol description](https://github.com/ndoa/Kelbi/blob/47c62ff8789105b36e73d0da8c37b4713b8dc27d/metalib/protocalhandler_tqqapi.xml), MIT: consulted for TPDU wire layout. Its license is reproduced in [third_party/kelbi/LICENSE](third_party/kelbi/LICENSE).
- [Arrowgene.MonsterHunterOnline](https://github.com/sebastian-heinz/Arrowgene.MonsterHunterOnline): consulted for the TqqApi AES / tsf4g padding format. The upstream project is AGPL-3.0; no upstream implementation files are included here. `tpdu.py` implements the observed wire format in this project.
- [uranami/roe_trace](https://github.com/uranami/roe_trace/blob/a0664ef3e6854518923f45edac053e75ea0412bf/src/message_names.inc): message names used as research hints only. The original file is not distributed here; it has no repository license identified at publication. Some optional probes may require a separately acquired reference.
- [Luigi Auriemma's dzs_qq.bms](https://aluigi.altervista.org/bms/dzs_qq.bms): consulted for archive format research; the external script is not distributed here.

These references do not grant rights to the original game or its assets. Other dependencies are installed separately and retain their respective licenses.
