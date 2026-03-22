"""cli-anything-blender — PyPI package setup."""

from setuptools import setup, find_namespace_packages

setup(
    name="cli-anything-blender",
    version="1.0.0",
    description="CLI harness for Blender 3D automation — part of the cli-anything suite",
    long_description=open("cli_anything/blender/README.md", encoding="utf-8").read()
        if __import__("os").path.exists("cli_anything/blender/README.md") else "",
    long_description_content_type="text/markdown",
    author="cli-anything",
    python_requires=">=3.10",
    packages=find_namespace_packages(include=["cli_anything.*"]),
    package_data={
        "cli_anything.blender": ["skills/*.md"],
    },
    install_requires=[
        "click>=8.0",
        "prompt_toolkit>=3.0",
        "Pillow>=10.0",
    ],
    entry_points={
        "console_scripts": [
            "cli-anything-blender=cli_anything.blender.blender_cli:cli",
        ],
    },
    classifiers=[
        "Programming Language :: Python :: 3",
        "License :: OSI Approved :: MIT License",
    ],
)
