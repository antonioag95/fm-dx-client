from setuptools import setup, find_packages

setup(
    name='fm-dx-client',
    version='1.0',
    packages=find_packages(),
    install_requires=open("requirements.txt").read().splitlines(),
    entry_points={
        'console_scripts': [
            'fm-dx-client = fm_dx_client.__main__:main'
        ]
    },
    author='antonioag95',
    description='A Python-based client for FM-DX Webserver sources. It displays FM Radio Data System (RDS) metadata, optionally plays the received MP3 audio locally using ffplay, and can optionally re-encode and restream the audio as AAC over HTTP using ffmpeg and aiohttp.',
    classifiers=[
        'Programming Language :: Python :: 3',
    ],
    python_requires='>=3.6',
)
