#!/bin/bash

# image name
image=hassioaddon-comfoair350

# registry
username="k42sde"
password=""
registry="registry-1.docker.io"

# ensure we're up to date
git pull

version=$(cat VERSION)
echo "build version: $version"

# run build
docker build -t "$image":latest .

# # tag it
# git add -A
# git commit -m "version $version"
# git tag -a "$version" -m "version $version"
# git push
# git push --tagsdocker tag $image:latest $image:$version

# push it
docker login --username="$username" --password="$password" "$registry"
docker image tag "$image":latest "$username"/"$image":latest
docker image tag "$image":latest "$username"/"$image":"$version"
docker push "$username"/"$image":latest
docker push "$username"/"$image":"$version"