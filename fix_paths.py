import glob, re

for f in glob.glob('**/*.py', recursive=True):
    with open(f, 'r', encoding='utf-8') as file:
        content = file.read()
    
    if 'ParcelPilot_Assessment_Data.xlsx' in content and 'g:/' in content.lower():
        if 'src' in f.replace('\\', '/'):
            repl = 'pathlib.Path(__file__).resolve().parent.parent / "ParcelPilot_Assessment_Data.xlsx"'
        else:
            repl = 'pathlib.Path(__file__).resolve().parent / "ParcelPilot_Assessment_Data.xlsx"'
            
        new_content = re.sub(r'[\'"]g:/ParcelPilot/ParcelPilot_Assessment_Data\.xlsx[\'"]', repl, content, flags=re.IGNORECASE)
        
        if 'import pathlib' not in new_content:
            new_content = 'import pathlib\n' + new_content
            
        with open(f, 'w', encoding='utf-8') as file:
            file.write(new_content)
        print(f'Updated {f}')
