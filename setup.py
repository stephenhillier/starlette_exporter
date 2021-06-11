from setuptools import setup

setup(
    name='starlette_exporter',
    version='0.9.0',
    author='Stephen Hillier',
    author_email='stephenhillier@gmail.com',
    packages=['starlette_exporter'],
    license='Apache License 2.0',
    url="https://github.com/stephenhillier/starlette_exporter",
    description='Prometheus metrics exporter for Starlette applications.',
    long_description=open('README.md').read(),
    long_description_content_type="text/markdown",
    install_requires=[
        "prometheus_client",
        "starlette"
    ],
)
