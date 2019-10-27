from distutils.core import setup

setup(
    name='starlette_exporter',
    version='0.1.0',
    author='Stephen Hillier',
    author_email='stephenhillier@gmail.com',
    packages=['starlette_exporter'],
    license='LICENSE',
    url="https://github.com/stephenhillier/starlette_exporter",
    description='Prometheus metrics exporter for Starlette applications.',
    long_description=open('README.md').read(),
    install_requires=[
        "prometheus_client",
        "starlette"
    ],
)
