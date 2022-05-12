#import  git 

#repo = git.Repo('name_of_repo')
#origin = repo.remote(name='origin')
#origin.pull()

import subprocess
subprocess.call(["git", "pull"])