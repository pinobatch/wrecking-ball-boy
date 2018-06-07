# -*- mode: python -*-

block_cipher = None


a = Analysis(['wbb.py'],
             pathex=['C:\\Users\\Pino\\develop\\wrecking-ball-boy'],
             binaries=[],
             datas=[
                 ('tilesets/*', 'tilesets'),
                 ('docs/*', 'docs'),
                 ('levels/*', 'levels'),
                 ('music/*', 'music'),
                 ('how.html', '.'),
                 ('README.md', '.'),
             ],
             hiddenimports=[],
             hookspath=[],
             runtime_hooks=[],
             excludes=[],
             win_no_prefer_redirects=False,
             win_private_assemblies=False,
             cipher=block_cipher)
pyz = PYZ(a.pure, a.zipped_data,
             cipher=block_cipher)
exe = EXE(pyz,
          a.scripts,
          exclude_binaries=True,
          name='wbb',
          debug=False,
          strip=False,
          upx=True,
          console=True )
coll = COLLECT(exe,
               a.binaries,
               a.zipfiles,
               a.datas,
               strip=False,
               upx=True,
               name='wbb')
