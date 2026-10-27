from setuptools import setup, find_packages

with open("requirements.txt") as f:
	install_requires = f.read().strip().split("\n")

# get version from __version__ variable in mjfsd_v3/__init__.py
from mjfsd_v3 import __version__ as version

setup(
	name="mjfsd_v3",
	version=version,
	description="This is site for MJFSD",
	author="Tech Ventures",
	author_email="safdar211@gmail.com",
	packages=find_packages(),
	zip_safe=False,
	include_package_data=True,
	install_requires=install_requires
)
