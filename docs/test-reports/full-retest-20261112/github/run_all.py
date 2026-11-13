import subprocess,pathlib
b=pathlib.Path(__file__).parent
for phase,script in [('search','run_stdio_live_test.py'),('prepare','run_stdio_live_test.py'),('finish','finish_stdio_source_test.py')]:
 cmd=['python3',str(b/script),str(b),phase]
 with (b/(phase+'.log')).open('w') as f: subprocess.run(cmd,stdout=f,stderr=subprocess.STDOUT,check=True)
 print(phase+' PASS',flush=True)
