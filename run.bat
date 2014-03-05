@ECHO OFF
IF EXIST .venv (
	call .venv\Scripts\activate
)
IF NOT EXIST server.ini (
	rem Copying new settings file from template.
	echo f | xcopy server.ini.sample server.ini
)
paster serve server.ini %*
